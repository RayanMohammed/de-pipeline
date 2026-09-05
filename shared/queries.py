UPSERT_QUERY = """
INSERT INTO patients (
    id, gender, birth_date, height_cm, weight_kg, bmi, bmi_category, latest_systolic_bp, latest_diastolic_bp, raw_bundle
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
ON CONFLICT (id) DO UPDATE SET
    gender = EXCLUDED.gender,
    birth_date = EXCLUDED.birth_date,
    height_cm = EXCLUDED.height_cm,
    weight_kg = EXCLUDED.weight_kg,
    bmi = EXCLUDED.bmi,
    bmi_category = EXCLUDED.bmi_category,
    latest_systolic_bp = EXCLUDED.latest_systolic_bp,
    latest_diastolic_bp = EXCLUDED.latest_diastolic_bp,
    raw_bundle = EXCLUDED.raw_bundle;
"""