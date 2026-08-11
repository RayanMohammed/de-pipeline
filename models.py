from pydantic import BaseModel


class PatientResponse(BaseModel):
    id: str
    gender: str | None = None
    birth_date: str | None = None

class PatientListResponse(BaseModel):
    patients: list[PatientResponse]