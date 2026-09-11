import datetime, json, os, uuid, uvicorn, asyncpg
from typing import Any
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Query, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from shared.extraction import extract_clinical_data, compute_bmi
from shared.models import ManualPatientIntake, ManualIntakeResponse
from shared.queries import (
    UPSERT_QUERY,
    OBSERVATION_UPSERT_QUERY,
    FIND_PATIENT_BY_NAME_DOB_QUERY,
    MANUAL_ENTRY_UPSERT_QUERY,
)

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=1,
        statement_cache_size=0,
    )
    yield
    await app.state.pool.close()

app = FastAPI(
    title="Clinical Data Platform API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_db():
    async with app.state.pool.acquire() as conn:
        yield conn

@app.get("/api/health")
async def health_check(conn: asyncpg.Connection = Depends(get_db)):
    row = await conn.fetchrow("SELECT 1 AS alive;")
    return {"status": "healthy", "database": row["alive"] == 1}

@app.get("/api/patients")
async def get_patients(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    gender: str | None = Query(None),
    bmi_category: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db),
):
    conditions = []
    params: list[Any] = []

    if gender:
        params.append(gender.lower())
        conditions.append(f"gender = ${len(params)}")

    if bmi_category:
        params.append(bmi_category.title())
        conditions.append(f"bmi_category = ${len(params)}")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    params.append(limit)
    limit_clause = f"LIMIT ${len(params)}"

    params.append(offset)
    offset_clause = f"OFFSET ${len(params)}"

    query = f"""
        SELECT 
            id, first_name, last_name, gender, birth_date, height_cm, weight_kg,
            bmi, bmi_category, latest_systolic_bp, latest_diastolic_bp
        FROM patients
        {where_clause}
        ORDER BY birth_date DESC
        {limit_clause} {offset_clause};
    """

    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]

@app.post("/api/patients/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_single_bundle(
    payload: dict[str, Any],
    conn: asyncpg.Connection = Depends(get_db),
):
    parsed = extract_clinical_data(payload)
    if not parsed:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Payload failed validation: missing Patient resource or invalid Bundle structure.",
        )

    patient = parsed["patient"]
    record_tuple = (
        uuid.UUID(str(patient["id"])),
        patient["gender"],
        patient["birth_date"],
        patient["height_cm"],
        patient["weight_kg"],
        patient["bmi"],
        patient["bmi_category"],
        patient["latest_systolic_bp"],
        patient["latest_diastolic_bp"],
        json.dumps(patient["raw_bundle"]) if patient["raw_bundle"] is not None else None,
    )

    await conn.execute(UPSERT_QUERY, *record_tuple)
    return {
        "status": "upserted",
        "patient_id": str(patient["id"]),
        "bmi": patient["bmi"],
        "bmi_category": patient["bmi_category"],
    }

@app.post(
    "/api/patients/manual-entry",
    status_code=status.HTTP_201_CREATED,
    response_model=ManualIntakeResponse,
)
async def manual_patient_entry(
    intake: ManualPatientIntake,
    conn: asyncpg.Connection = Depends(get_db),
):
    # Same first/last name + birth date is treated as the same person, not a new patient.
    # This prevents doctor re-submitting the form from creating duplicate patient 
    # rows with two different random UUIDs.
    existing = await conn.fetchrow(
        FIND_PATIENT_BY_NAME_DOB_QUERY,
        intake.first_name,
        intake.last_name,
        intake.birth_date,
    )
    matched_existing = existing is not None
    patient_id = existing["id"] if matched_existing else uuid.uuid4()

    bmi, bmi_category = compute_bmi(intake.height_cm, intake.weight_kg)

    await conn.execute(
        MANUAL_ENTRY_UPSERT_QUERY,
        patient_id,
        intake.first_name,
        intake.last_name,
        intake.gender,
        intake.birth_date,
        intake.height_cm,
        intake.weight_kg,
        bmi,
        bmi_category,
        intake.systolic_bp,
        intake.diastolic_bp,
    )

    # Every vital the doctor actually filled in also becomes its own row in
    # the 'observations' table, using the same LOINC codes the FHIR pipeline uses.
    # This allows a manually entered visit to show up in the Vitals Progression chart
    # in Tableau alongside the Synthea-imported history for a patient, instead of only 
    # updating the "latest" snapshot on the patients row.
    obs_date = intake.observation_date or datetime.date.today()
    observation_rows = []
    if intake.height_cm is not None:
        observation_rows.append((uuid.uuid4(), patient_id, "8302-2", "Body Height", intake.height_cm, "cm", obs_date))
    if intake.weight_kg is not None:
        observation_rows.append((uuid.uuid4(), patient_id, "29463-7", "Body Weight", intake.weight_kg, "kg", obs_date))
    if intake.systolic_bp is not None:
        observation_rows.append((uuid.uuid4(), patient_id, "8480-6", "Systolic Blood Pressure", intake.systolic_bp, "mm[Hg]", obs_date))
    if intake.diastolic_bp is not None:
        observation_rows.append((uuid.uuid4(), patient_id, "8462-4", "Diastolic Blood Pressure", intake.diastolic_bp, "mm[Hg]", obs_date))

    if observation_rows:
        await conn.executemany(OBSERVATION_UPSERT_QUERY, observation_rows)

    return ManualIntakeResponse(
        patient_id=patient_id,
        matched_existing_patient=matched_existing,
        bmi=bmi,
        bmi_category=bmi_category,
        observations_recorded=len(observation_rows),
    )
