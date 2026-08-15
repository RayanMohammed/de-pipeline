import os, uvicorn
from dotenv import load_dotenv
from supabase import create_client
from fastapi import FastAPI, HTTPException
from models import PatientListResponse

load_dotenv()
app = FastAPI(title="FHIR Pipeline")
url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase = create_client(url, key)

@app.get("/")
def home():
    return "API is online"

@app.get("/patients", response_model=PatientListResponse)
def get_patients(
    gender:str | None = None,
    age:str | None = None
):
    results = supabase.table('patients').select('*')

    if gender:
        results = results.eq("gender", gender)

    if age == "asc":
        results = results.order("birth_date", desc=False)
    elif age == "desc":
        results = results.order("birth_date", desc=True)

    results = results.execute()
    return {"patients": results.data}