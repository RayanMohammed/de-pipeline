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

load_dotenv()

R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL")
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID")
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY")
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "clinical-data-lake")
DATABASE_URL = os.getenv("DATABASE_URL")
ARCHIVE_KEY = "synthea_sample.tar.gz"

query = """
INSERT INTO patients (id, gender, birth_date, height_cm, weight_kg, bmi, bmi_category,latest_systolic_bp, latest_diastolic_bp, raw_bundle)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
ON CONFLICT (id) DO UPDATE SET 
    gender = EXCLUDED.gender,
    birth_date = EXCLUDED.birth_date,
    height_cm = EXCLUDED.height_cm,
    weight_kg = EXCLUDED.weight_kg,
    bmi = EXCLUDED.bmi,
    bmi_category = EXCLUDED.bmi_category,
    latest_systolic_bp = EXCLUDED.latest_systolic_bp,
    latest_diastolic_bp = EXCLUDED.latest_diastolic_bp,
    raw_bundle = EXCLUDED.raw_bundle;
"""

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