import json, os, uuid, uvicorn, asyncpg
from typing import Any
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Query, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from shared.extraction import extract_clinical_data
from shared.queries import UPSERT_QUERY

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
            id, gender, birth_date, height_cm, weight_kg,
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

    record_tuple = (
        uuid.UUID(str(parsed["id"])),
        parsed["gender"],
        parsed["birth_date"],
        parsed["height_cm"],
        parsed["weight_kg"],
        parsed["bmi"],
        parsed["bmi_category"],
        parsed["latest_systolic_bp"],
        parsed["latest_diastolic_bp"],
        json.dumps(parsed["raw_bundle"]),
    )

    await conn.execute(UPSERT_QUERY, *record_tuple)
    return {
        "status": "upserted",
        "patient_id": str(parsed["id"]),
        "bmi": parsed["bmi"],
        "bmi_category": parsed["bmi_category"],
    }