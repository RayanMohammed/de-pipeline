"""
Packages a local directory of Synthea FHIR output into a .tar.gz and uploads
it to R2 under a caller-specified key -- a small, separate step between
"Synthea ran" and "batch_ingest.py can process this," rather than folding
upload logic into either of those.

Synthea's FHIR exporter also writes hospitalInformation*.json and
practitionerInformation*.json alongside the per-patient bundles -- valid FHIR
Bundles, but with no Patient resource in them. batch_ingest.py's DLQ would
handle those correctly (no crash), but every run would produce two DLQ
entries that aren't real problems, just noise. Filtered out here so the DLQ
only ever reflects genuine anomalies.
"""
import argparse
import os
import tarfile

import boto3

R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "clinical-data-lake")

NON_PATIENT_PREFIXES = ("hospitalInformation", "practitionerInformation")


def parse_args():
    parser = argparse.ArgumentParser(description="Package Synthea output and upload it to R2.")
    parser.add_argument("--source-dir", required=True, help="Directory of Synthea FHIR JSON output.")
    parser.add_argument("--archive-key", required=True, help="R2 object key to upload the archive as.")
    return parser.parse_args()


def build_archive(source_dir: str, archive_path: str) -> int:
    """Tars every patient JSON file in source_dir, skipping the non-patient
    reference files. Returns how many files were included."""
    included = 0
    with tarfile.open(archive_path, "w:gz") as tar:
        for filename in sorted(os.listdir(source_dir)):
            if not filename.endswith(".json"):
                continue
            if filename.startswith(NON_PATIENT_PREFIXES):
                continue
            tar.add(os.path.join(source_dir, filename), arcname=filename)
            included += 1
    return included


def main():
    args = parse_args()
    archive_path = "/tmp/synthea_batch.tar.gz"

    included = build_archive(args.source_dir, archive_path)
    print(f"Packaged {included} patient files into {archive_path}")

    s3 = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT_URL,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )
    with open(archive_path, "rb") as f:
        s3.put_object(Bucket=R2_BUCKET_NAME, Key=args.archive_key, Body=f)
    print(f"Uploaded to R2 as {args.archive_key}")


if __name__ == "__main__":
    main()
