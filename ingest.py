import json
from models import Patient, BundleEntry, Bundle

with open("data/Alberto639_Tromp100_aa1a2074-ad05-6d4f-0063-6188c4f25a12 copy.json", "r") as file:
    new_dict = json.load(file)
    fhir_bundle = Bundle(**new_dict)
    for item in fhir_bundle.entry:
        if item.resource.get("resourceType") == "Patient":
            unpacked = Patient(**item.resource)


print(unpacked.id)
