import json, psycopg2, os
from models import Patient, BundleEntry, Bundle
from dotenv import load_dotenv

load_dotenv()

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
curs = conn.cursor()
query = "INSERT INTO patients (id, resource_type) VALUES (%s, %s)"

with open("data/Alberto639_Tromp100_aa1a2074-ad05-6d4f-0063-6188c4f25a12 copy.json", "r") as file:
    new_dict = json.load(file)
    fhir_bundle = Bundle(**new_dict)
    for item in fhir_bundle.entry:
        if item.resource.get("resourceType") == "Patient":
            unpacked = Patient(**item.resource)
            curs.execute(query, (unpacked.id, unpacked.resourceType))

conn.commit()
curs.close()
conn.close()

print(unpacked.id)
