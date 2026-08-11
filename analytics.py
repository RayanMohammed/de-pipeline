import duckdb
import pandas as pd
import glob, json

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
    flattened_entry.resource.birthDate AS birth_date,
    flattened_entry.resource.resourceType AS resource_type
FROM (
    SELECT 
        UNNEST(entry) as flattened_entry
    FROM read_json_auto({valid_files})
)
WHERE flattened_entry.resource.resourceType = 'Patient'
"""

conn = duckdb.connect()
df = conn.execute(query).df()

print(df)