import datetime, json, os, uuid, uvicorn, asyncpg
from typing import Any
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Query, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from shared.extraction import extract_clinical_data, compute_bmi
from shared.models import (
    ManualPatientIntake,
    ManualIntakeResponse,
    PatientMatchResponse,
    PatientSnapshot,
    ObservationHistoryEntry,
)
from shared.queries import (
    UPSERT_QUERY,
    OBSERVATION_UPSERT_QUERY,
    FIND_PATIENT_BY_NAME_DOB_QUERY,
    MANUAL_ENTRY_UPSERT_QUERY,
    OBSERVATIONS_BY_PATIENT_QUERY,
    PATIENT_BY_ID_QUERY,
)

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
# Defaults to 1 -- the Supabase free-tier accommodation from earlier. Overridable
# via env var so a load-test experiment can compare pool sizes without editing
# and reverting this file between runs.
POOL_MAX_SIZE = int(os.getenv("POOL_MAX_SIZE", "1"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=1,
        max_size=POOL_MAX_SIZE,
        statement_cache_size=0,
    )
    print(
        f"[startup] pool ready: min_size={app.state.pool.get_min_size()} "
        f"max_size={app.state.pool.get_max_size()} "
        f"(POOL_MAX_SIZE env={POOL_MAX_SIZE}) "
        f"host={DATABASE_URL.split('@')[-1].split('/')[0] if DATABASE_URL else None}"
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
    order_by: str = Query("birth_date", pattern="^(birth_date|created_at)$"),
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

    order_column = {"birth_date": "birth_date", "created_at": "created_at"}[order_by]

    query = f"""
        SELECT 
            id, first_name, last_name, gender, birth_date, height_cm, weight_kg,
            bmi, bmi_category, latest_systolic_bp, latest_diastolic_bp, created_at
        FROM patients
        {where_clause}
        ORDER BY {order_column} DESC
        {limit_clause} {offset_clause};
    """

    rows = await conn.fetch(query, *params)
    return [dict(row) for row in rows]

@app.get("/api/patients/lookup", response_model=PatientMatchResponse)
async def lookup_patient_by_name_dob(
    first_name: str,
    last_name: str,
    birth_date: datetime.date,
    conn: asyncpg.Connection = Depends(get_db),
):
    existing = await conn.fetchrow(
        FIND_PATIENT_BY_NAME_DOB_QUERY,
        first_name.strip(),
        last_name.strip(),
        birth_date,
    )
    return PatientMatchResponse(
        match_found=existing is not None,
        patient=PatientSnapshot(**dict(existing)) if existing else None,
    )

@app.get("/api/patients/{patient_id}/observations", response_model=list[ObservationHistoryEntry])
async def get_patient_observations(
    patient_id: uuid.UUID,
    conn: asyncpg.Connection = Depends(get_db),
):
    rows = await conn.fetch(OBSERVATIONS_BY_PATIENT_QUERY, patient_id)
    return [ObservationHistoryEntry(**dict(row)) for row in rows]

@app.get("/api/patients/{patient_id}", response_model=PatientSnapshot)
async def get_patient_by_id(
    patient_id: uuid.UUID,
    conn: asyncpg.Connection = Depends(get_db),
):
    row = await conn.fetchrow(PATIENT_BY_ID_QUERY, patient_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No patient exists with that id.",
        )
    return PatientSnapshot(**dict(row))

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
    existing = None
    if not intake.force_new:
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
