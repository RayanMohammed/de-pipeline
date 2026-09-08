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

CREATE TABLE IF NOT EXISTS observations (
    id UUID PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES patients(id),
    observation_code TEXT NOT NULL,
    observation_description TEXT,
    observation_value NUMERIC(10, 2),
    observation_unit TEXT,
    observation_date DATE
);
CREATE INDEX IF NOT EXISTS observations_patient_code_date_idx
    ON observations(patient_id, observation_code, observation_date);

CREATE TABLE IF NOT EXISTS conditions (
    id UUID PRIMARY KEY,
    patient_id UUID NOT NULL REFERENCES patients(id),
    condition_code TEXT NOT NULL,
    condition_description TEXT,
    start_date DATE NOT NULL,
    end_date DATE
);
CREATE INDEX IF NOT EXISTS conditions_patient_code_idx
    ON conditions(patient_id, condition_code);