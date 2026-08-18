from pydantic import BaseModel


class PatientResponse(BaseModel):
    id: str
    gender: str | None = None
    birth_date: str | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    bmi: float | None = None
    bmi_category: str | None = None

class PatientListResponse(BaseModel):
    patients: list[PatientResponse]