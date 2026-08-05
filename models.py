from pydantic import BaseModel


class Patient(BaseModel):
    id: str
    resourceType: str


class BundleEntry(BaseModel):
    resource: dict


class Bundle(BaseModel):
    resourceType: str
    entry: list[BundleEntry]
