from pydantic import BaseModel, ConfigDict, Field
import datetime, uuid

class PatientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    gender: str | None = None
    birth_date: datetime.date | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    bmi: float | None = None
    bmi_category: str | None = None
    latest_systolic_bp: int | None = None
    latest_diastolic_bp: int | None = None
    raw_bundle: dict | None = None

class PatientListResponse(BaseModel):
    patients: list[PatientResponse]

class ObservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    observation_code: str
    observation_value: float | None = None
    observation_description: str | None = None
    observation_unit: str | None = None
    observation_date: datetime.date | None = None

class ConditionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    patient_id: uuid.UUID
    condition_code: str 
    condition_description: str | None = None
    start_date: datetime.date 
    end_date: datetime.date | None = None

class ManualPatientIntake(BaseModel):
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    gender: str | None = None
    birth_date: datetime.date
    height_cm: float | None = Field(default=None, gt=0, le=300)
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    systolic_bp: int | None = Field(default=None, ge=40, le=300)
    diastolic_bp: int | None = Field(default=None, ge=20, le=200)
    observation_date: datetime.date | None = None

class ManualIntakeResponse(BaseModel):
    patient_id: uuid.UUID
    matched_existing_patient: bool
    bmi: float | None = None
    bmi_category: str | None = None
    observations_recorded: int
