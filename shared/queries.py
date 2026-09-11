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

OBSERVATION_UPSERT_QUERY = """
INSERT INTO observations (
    id, patient_id, observation_code, observation_description, observation_value, observation_unit, observation_date
)
VALUES ($1, $2, $3, $4, $5, $6, $7)
ON CONFLICT (id) DO UPDATE SET
    patient_id = EXCLUDED.patient_id,
    observation_code = EXCLUDED.observation_code,
    observation_description = EXCLUDED.observation_description,
    observation_value = EXCLUDED.observation_value,
    observation_unit = EXCLUDED.observation_unit,
    observation_date = EXCLUDED.observation_date;
"""

CONDITION_UPSERT_QUERY = """
INSERT INTO conditions (
    id, patient_id, condition_code, condition_description, start_date, end_date
)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (id) DO UPDATE SET
    patient_id = EXCLUDED.patient_id,
    condition_code = EXCLUDED.condition_code,
    condition_description = EXCLUDED.condition_description,
    start_date = EXCLUDED.start_date,
    end_date = EXCLUDED.end_date;
"""

FIND_PATIENT_BY_NAME_DOB_QUERY = """
SELECT id FROM patients
WHERE lower(first_name) = lower($1)
  AND lower(last_name) = lower($2)
  AND birth_date = $3;
"""

MANUAL_ENTRY_UPSERT_QUERY = """
INSERT INTO patients (
    id, first_name, last_name, gender, birth_date,
    height_cm, weight_kg, bmi, bmi_category,
    latest_systolic_bp, latest_diastolic_bp
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
ON CONFLICT (id) DO UPDATE SET
    first_name = COALESCE(EXCLUDED.first_name, patients.first_name),
    last_name = COALESCE(EXCLUDED.last_name, patients.last_name),
    gender = COALESCE(EXCLUDED.gender, patients.gender),
    birth_date = COALESCE(EXCLUDED.birth_date, patients.birth_date),
    height_cm = COALESCE(EXCLUDED.height_cm, patients.height_cm),
    weight_kg = COALESCE(EXCLUDED.weight_kg, patients.weight_kg),
    bmi = COALESCE(EXCLUDED.bmi, patients.bmi),
    bmi_category = COALESCE(EXCLUDED.bmi_category, patients.bmi_category),
    latest_systolic_bp = COALESCE(EXCLUDED.latest_systolic_bp, patients.latest_systolic_bp),
    latest_diastolic_bp = COALESCE(EXCLUDED.latest_diastolic_bp, patients.latest_diastolic_bp);
"""
