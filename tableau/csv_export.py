import asyncio
import csv
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__))

COHORT_QUERY = """
SELECT
    p.id,
    p.gender,
    p.birth_date,
    p.height_cm,
    p.weight_kg,
    p.bmi,
    p.bmi_category,
    p.latest_systolic_bp,
    p.latest_diastolic_bp,
    COUNT(c.id) AS condition_count
FROM patients p
LEFT JOIN conditions c ON c.patient_id = p.id
GROUP BY p.id, p.gender, p.birth_date, p.height_cm, p.weight_kg,
         p.bmi, p.bmi_category, p.latest_systolic_bp, p.latest_diastolic_bp
"""

OBSERVATIONS_QUERY = """
SELECT patient_id, observation_code, observation_description,
       observation_value, observation_unit, observation_date
FROM observations
ORDER BY patient_id, observation_date
"""

CONDITIONS_QUERY = """
SELECT patient_id, condition_code, condition_description, start_date, end_date
FROM conditions
ORDER BY patient_id, start_date
"""


async def export_query(conn, query: str, filename: str):
    rows = await conn.fetch(query)
    if not rows:
        print(f"No rows for {filename}, skipping.")
        return
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow(row.values())
    print(f"Wrote {len(rows)} rows -> {path}")


async def main():
    conn = await asyncpg.connect(DATABASE_URL)
    try:
        await export_query(conn, COHORT_QUERY, "cohort_summary.csv")
        await export_query(conn, OBSERVATIONS_QUERY, "observations_timeseries.csv")
        await export_query(conn, CONDITIONS_QUERY, "conditions.csv")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
