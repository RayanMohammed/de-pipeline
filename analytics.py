# NOTE: This script is for local ETL execution and testing. 
# For cloud-based ingestion, please refer to the 
# Google Colab notebook in this repository.

import duckdb
import pandas as pd
import glob, json, os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)

full_list = glob.glob('data/*.json')
valid_files = []

for item in full_list:
    try:
        with open(item, 'r') as file:
            new_dict = json.load(file)
        
        valid_files.append(item)
    except Exception as e:
        pass


query = f"""
SELECT 
    flattened_entry.resource.id AS id,
    flattened_entry.resource.gender AS gender,
    flattened_entry.resource.birthDate AS birth_date
FROM (
    SELECT 
        UNNEST(entry) as flattened_entry
    FROM read_json_auto({valid_files})
)
WHERE flattened_entry.resource.resourceType = 'Patient'
"""

conn = duckdb.connect()
df = conn.execute(query).df()

df['id'] = df['id'].astype(str)
if 'birth_date' in df.columns:
    df['birth_date'] = df['birth_date'].astype(str)

records = df.to_dict(orient="records")

supabase.table('patients').insert(records).execute()
print(f"inserted {len(records)} records into supabase")