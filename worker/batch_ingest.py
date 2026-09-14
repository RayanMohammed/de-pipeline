import argparse
import asyncio
import io
import json
import os
import tarfile
import uuid
import asyncpg
import boto3
from dotenv import load_dotenv
from shared.extraction import extract_clinical_data
from shared.queries import UPSERT_QUERY, OBSERVATION_UPSERT_QUERY, CONDITION_UPSERT_QUERY

load_dotenv()

R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "clinical-data-lake")
DATABASE_URL = os.getenv("DATABASE_URL")
DEFAULT_ARCHIVE_KEY = "synthea_subset.tar.gz"


def parse_args():
    parser = argparse.ArgumentParser(description="Ingest a FHIR bundle archive from R2 into Postgres.")
    parser.add_argument(
        "--archive-key", default=DEFAULT_ARCHIVE_KEY,
        help="R2 object key of the .tar.gz archive to ingest (default: the original historical archive).",
    )
    parser.add_argument(
        "--ingestion-run-id", default=None,
        help="Tag written onto every patient row from this run (e.g. a scheduled-ingestion run id). "
             "Omitted for the original manual/historical invocation.",
    )
    return parser.parse_args()

def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT_URL,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )

def send_to_dlq(s3_client, file_name: str, raw_content: str, error_reason: str):
    dlq_payload = {"error": error_reason, "raw_content": raw_content}
    s3_client.put_object(
        Bucket=R2_BUCKET_NAME,
        Key=f"dlq_errors/{file_name}",
        Body=json.dumps(dlq_payload, indent=2),
        ContentType="application/json",
    )
    print(f"--> Diverted to DLQ [{file_name}]: {error_reason}")

async def main():
    args = parse_args()
    archive_key = args.archive_key
    ingestion_run_id = args.ingestion_run_id

    s3 = get_r2_client()

    print(f"Fetching {archive_key} from R2 into memory...")
    if ingestion_run_id:
        print(f"Tagging every row from this run with ingestion_run_id={ingestion_run_id}")
    response = s3.get_object(Bucket=R2_BUCKET_NAME, Key=archive_key)
    raw_archive_bytes = response["Body"].read()
    byte_stream = io.BytesIO(raw_archive_bytes)

    print("Connecting to PostgreSQL via asyncpg...")
    # statement_cache_size=0: required if DATABASE_URL points at Supabase's
    # transaction-mode pooler rather than a direct connection -- asyncpg's
    # default prepared-statement caching assumes one connection maps to one
    # stable backend, which a transaction pooler doesn't guarantee across
    # this script's sequential chunked transactions. Same fix api/main.py
    # already applies for its pool.
    conn = await asyncpg.connect(DATABASE_URL, statement_cache_size=0)

    batch_records = []
    observation_batch = []
    condition_batch = []
    total_upserted = 0
    total_dlq = 0

    try:
        with tarfile.open(fileobj=byte_stream, mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile() or not member.name.endswith(".json"):
                    continue

                filename = os.path.basename(member.name)

                # skip hidden OS metadata files
                if filename.startswith("._") or filename.startswith("."):
                    continue

                extracted = tar.extractfile(member)
                if not extracted:
                    continue

                raw_bytes = extracted.read()

                try:
                    raw_text = raw_bytes.decode("utf-8")
                    bundle_dict = json.loads(raw_text)
                except UnicodeDecodeError as err:
                    safe_preview = raw_bytes.decode("utf-8", errors="replace")
                    send_to_dlq(
                        s3,
                        filename,
                        safe_preview,
                        f"Encoding error: {err}"
                    )
                    total_dlq += 1
                    continue
                except Exception as err:
                    safe_preview = raw_bytes.decode("utf-8", errors="replace")
                    send_to_dlq(
                        s3,
                        filename,
                        safe_preview,
                        f"JSON decode error: {err}",
                    )
                    total_dlq += 1
                    continue

                try:
                    parsed = extract_clinical_data(bundle_dict)
                    if parsed is None:
                        send_to_dlq(
                            s3,
                            filename,
                            raw_text,
                            "Extraction returned None (missing Patient or invalid Bundle)",
                        )
                        total_dlq += 1
                        continue

                    patient = parsed["patient"]
                    record_tuple = (
                        uuid.UUID(str(patient["id"])),
                        patient["gender"],
                        patient["birth_date"],
                        patient["height_cm"],
                        patient["weight_kg"],
                        patient["bmi"],
                        patient["bmi_category"],
                        patient["latest_systolic_bp"],
                        patient["latest_diastolic_bp"],
                        json.dumps(patient["raw_bundle"]) if patient["raw_bundle"] is not None else None,
                        ingestion_run_id,
                    )
                    batch_records.append(record_tuple)

                    for obs in parsed["observations"]:
                        observation_batch.append((
                            obs["id"],
                            obs["patient_id"],
                            obs["observation_code"],
                            obs["observation_description"],
                            obs["observation_value"],
                            obs["observation_unit"],
                            obs["observation_date"],
                        ))

                    for cond in parsed["conditions"]:
                        condition_batch.append((
                            cond["id"],
                            cond["patient_id"],
                            cond["condition_code"],
                            cond["condition_description"],
                            cond["start_date"],
                            cond["end_date"],
                        ))

                    total_upserted += 1

                except Exception as err:
                    send_to_dlq(s3, filename, raw_text, f"Extraction exception: {err}")
                    total_dlq += 1
                    continue

                if len(batch_records) >= 500:
                    # All three writes for a chunk succeed or none do -- a crash
                    # partway through can't leave a patient row without its
                    # observations/conditions.
                    async with conn.transaction():
                        await conn.executemany(UPSERT_QUERY, batch_records)
                        await conn.executemany(OBSERVATION_UPSERT_QUERY, observation_batch)
                        await conn.executemany(CONDITION_UPSERT_QUERY, condition_batch)
                    print(f"Upserted chunk of {len(batch_records)} patients, {len(observation_batch)} observations, {len(condition_batch)} conditions...")
                    batch_records.clear()
                    observation_batch.clear()
                    condition_batch.clear()

            if batch_records:
                async with conn.transaction():
                    await conn.executemany(UPSERT_QUERY, batch_records)
                    await conn.executemany(OBSERVATION_UPSERT_QUERY, observation_batch)
                    await conn.executemany(CONDITION_UPSERT_QUERY, condition_batch)
                print(f"Upserted final chunk of {len(batch_records)} patients, {len(observation_batch)} observations, {len(condition_batch)} conditions.")

        print(
            f"\nRun Complete: {total_upserted} records upserted to DB, {total_dlq} records isolated in DLQ."
        )

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())