import os, uvicorn
from dotenv import load_dotenv
from supabase import create_client
from fastapi import FastAPI, Query
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
    min_bmi:float | None = Query(default=None, description="Filter patients with BMI greater than or equal to this value"),
    age:str | None = Query(default=None, pattern="^(asc|desc)$")
):
    results = supabase.table('patients').select('*')

    if gender:
        results = results.eq("gender", gender)

    if min_bmi is not None:
        results = results.eq("bmi", min_bmi)

    if age == "asc":
        results = results.order("birth_date", desc=False)
    elif age == "desc":
        results = results.order("birth_date", desc=True)

    results = results.execute()
    return {"patients": results.data}