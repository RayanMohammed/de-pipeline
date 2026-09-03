from pydantic import BaseModel, ConfigDict
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