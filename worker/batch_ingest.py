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
from shared.queries import UPSERT_QUERY

load_dotenv()

R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "clinical-data-lake")
DATABASE_URL = os.getenv("DATABASE_URL")
ARCHIVE_KEY = "synthea_sample.tar.gz"

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
    s3 = get_r2_client()

    print(f"Fetching {ARCHIVE_KEY} from R2 into memory...")
    response = s3.get_object(Bucket=R2_BUCKET_NAME, Key=ARCHIVE_KEY)
    raw_archive_bytes = response["Body"].read()
    byte_stream = io.BytesIO(raw_archive_bytes)

    print("Connecting to PostgreSQL via asyncpg...")
    conn = await asyncpg.connect(DATABASE_URL)

    batch_records = []
    total_upserted = 0
    total_dlq = 0

    try:
        with tarfile.open(fileobj=byte_stream, mode="r:gz") as tar:
            for member in tar.getmembers():
                if not member.isfile() or not member.name.endswith(".json"):
                    continue

                filename = os.path.basename(member.name)

                # Skip hidden OS metadata files (macOS AppleDouble files)
                if filename.startswith("._") or filename.startswith("."):
                    continue

                extracted = tar.extractfile(member)
                if not extracted:
                    continue

                raw_bytes = extracted.read()

                # Layer 1: Text decoding & JSON syntax validation
                try:
                    raw_text = raw_bytes.decode("utf-8")
                    bundle_dict = json.loads(raw_text)
                except UnicodeDecodeError as err:
                    safe_preview = raw_bytes.decode("utf-8", errors="replace")
                    send_to_dlq(s3, filename, safe_preview, f"Encoding error: {err}")
                    total_dlq += 1
                    continue
                except Exception as err:
                    send_to_dlq(
                        s3,
                        filename,
                        raw_bytes.decode("utf-8", errors="replace"),
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

                    record_tuple = (
                        uuid.UUID(str(parsed["id"])),
                        parsed["gender"],
                        parsed["birth_date"],
                        parsed["height_cm"],
                        parsed["weight_kg"],
                        parsed["bmi"],
                        parsed["bmi_category"],
                        parsed["latest_systolic_bp"],
                        parsed["latest_diastolic_bp"],
                        json.dumps(parsed["raw_bundle"]),
                    )
                    batch_records.append(record_tuple)
                    total_upserted += 1

                except Exception as err:
                    send_to_dlq(s3, filename, raw_text, f"Extraction exception: {err}")
                    total_dlq += 1
                    continue
                if len(batch_records) >= 500:
                    await conn.executemany(UPSERT_QUERY, batch_records)
                    print(f"Upserted chunk of {len(batch_records)} records...")
                    batch_records.clear()

            if batch_records:
                await conn.executemany(UPSERT_QUERY, batch_records)
                print(f"Upserted final chunk of {len(batch_records)} records.")

        print(
            f"\nRun Complete: {total_upserted} records upserted to DB, {total_dlq} records isolated in DLQ."
        )

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())