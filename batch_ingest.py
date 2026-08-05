import json, psycopg2
from models import Patient, BundleEntry, Bundle
from pathlib import Path

data_dir = Path("data")

conn = psycopg2.connect(dbname="postgres", user="postgres", password="postgres", host="localhost", port=5432)
curs = conn.cursor()
query = "INSERT INTO patients (id, resource_type) VALUES (%s, %s)"

try:
    for item in data_dir.glob("*.json"):
        try:
            with item.open("r") as file:
                new_dict = json.load(file)
                fhir_bundle = Bundle(**new_dict)
                for info in fhir_bundle.entry:
                    if info.resource.get("resourceType") == "Patient":
                        unpacked = Patient(**info.resource)
                        curs.execute(query, (unpacked.id, unpacked.resourceType))
            
            conn.commit()

        except Exception as e:
            conn.rollback()
            print(f"error occurred, {item.name}: {e}")
finally:
    curs.close()
    conn.close()