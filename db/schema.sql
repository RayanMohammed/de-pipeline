CREATE TABLE IF NOT EXISTS patients (
    id UUID PRIMARY KEY,
    gender TEXT,
    birth_date DATE,
    height_cm NUMERIC(5, 2),
    weight_kg NUMERIC(5, 2),
    bmi NUMERIC(4, 1),
    bmi_category TEXT,
    latest_systolic_bp INTEGER,
    latest_diastolic_bp INTEGER,
    raw_bundle JSONB
);
CREATE INDEX IF NOT EXISTS patients_gender_bmi_idx ON patients(gender, bmi);
CREATE INDEX IF NOT EXISTS patients_birth_date_idx ON patients(birth_date);
CREATE INDEX IF NOT EXISTS patients_systolic_bp_idx ON patients(latest_systolic_bp);
CREATE INDEX IF NOT EXISTS patients_diastolic_bp_idx ON patients(latest_diastolic_bp);