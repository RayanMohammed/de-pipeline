from pydantic import BaseModel, ConfigDict, Field, model_validator
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
    force_new: bool = Field(default=False)

    @model_validator(mode="after")
    def normalize_and_validate_intake(self):
        self.first_name = self.first_name.strip().title()
        self.last_name = self.last_name.strip().title()

        if self.height_cm is not None and self.weight_kg is not None:
            bmi = self.weight_kg / ((self.height_cm / 100) ** 2)
            if not (10 <= bmi <= 200):
                raise ValueError(
                    f"Height/weight combination produces an invalid BMI ({bmi:.1f}). "
                    "Please double-check the height and weight values."
                )
        return self

class ManualIntakeResponse(BaseModel):
    patient_id: uuid.UUID
    matched_existing_patient: bool
    bmi: float | None = None
    bmi_category: str | None = None
    observations_recorded: int

class PatientSnapshot(BaseModel):
    id: uuid.UUID
    first_name: str | None = None
    last_name: str | None = None
    gender: str | None = None
    birth_date: datetime.date | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    bmi: float | None = None
    bmi_category: str | None = None
    latest_systolic_bp: int | None = None
    latest_diastolic_bp: int | None = None

class PatientMatchResponse(BaseModel):
    match_found: bool
    patient: PatientSnapshot | None = None

class ObservationHistoryEntry(BaseModel):
    observation_code: str
    observation_description: str | None = None
    observation_value: float | None = None
    observation_unit: str | None = None
    observation_date: datetime.date | None = None

class BmiDistribution(BaseModel):
    underweight: int
    normal: int
    overweight: int
    obese: int

class PatientStats(BaseModel):
    total_patients: int
    avg_bmi: float | None = None
    bmi_distribution: BmiDistribution
    most_recent_patient_at: datetime.datetime | None = None

class RecentActivityEntry(BaseModel):
    patient_id: uuid.UUID
    first_name: str | None = None
    last_name: str | None = None
    observation_description: str | None = None
    observation_value: float | None = None
    observation_unit: str | None = None
    observation_date: datetime.date | None = None
