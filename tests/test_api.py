import pytest, uuid
from httpx import ASGITransport, AsyncClient
from api.main import app, lifespan

@pytest.mark.anyio
async def test_health_check():
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["database"] is True

@pytest.mark.anyio
async def test_get_patients_query_limit():
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/patients?limit=5&offset=0")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) <= 5

@pytest.mark.anyio
async def test_ingest_valid_bundle():
    p_id = str(uuid.uuid4())
    valid_payload = {
        "resourceType": "Bundle",
        "entry": [
            {
                "resource": {
                    "resourceType": "Patient",
                    "id": p_id,
                    "gender": "female",
                    "birthDate": "1995-06-12",
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": str(uuid.uuid4()),
                    "effectiveDateTime": "2024-03-01T00:00:00Z",
                    "code": {"coding": [{"code": "8302-2"}]},
                    "valueQuantity": {"value": 165.0},
                }
            },
            {
                "resource": {
                    "resourceType": "Observation",
                    "id": str(uuid.uuid4()),
                    "effectiveDateTime": "2024-03-01T00:00:00Z",
                    "code": {"coding": [{"code": "29463-7"}]},
                    "valueQuantity": {"value": 60.0},
                }
            },
        ],
    }
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/patients/ingest", json=valid_payload
            )
            assert response.status_code == 201
            data = response.json()
            assert data["status"] == "upserted"
            assert data["patient_id"] == p_id
            assert data["bmi"] == 22.0
            assert data["bmi_category"] == "Normal"

@pytest.mark.anyio
async def test_ingest_invalid_bundle():
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # missing Patient resource
            invalid_payload = {
                "resourceType": "Bundle",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "Observation",
                            "code": {"coding": [{"code": "8302-2"}]},
                        }
                    }
                ],
            }
            response = await client.post(
                "/api/patients/ingest", json=invalid_payload
            )
            assert response.status_code == 422
            assert "Payload failed validation" in response.json()["detail"]

@pytest.mark.anyio
async def test_manual_entry_creates_new_patient():
    unique_last = f"Testerson{uuid.uuid4().hex[:8]}"
    payload = {
        "first_name": "Jane",
        "last_name": unique_last,
        "gender": "female",
        "birth_date": "1988-04-12",
        "height_cm": 165.0,
        "weight_kg": 60.0,
        "systolic_bp": 118,
        "diastolic_bp": 76,
    }
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/patients/manual-entry", json=payload)
            assert response.status_code == 201
            data = response.json()
            assert data["matched_existing_patient"] is False
            assert data["bmi"] == 22.0
            assert data["bmi_category"] == "Normal"
            assert data["observations_recorded"] == 4

@pytest.mark.anyio
async def test_manual_entry_matches_existing_patient_by_name_dob():
    unique_last = f"Dupecheck{uuid.uuid4().hex[:8]}"
    payload = {
        "first_name": "Sam",
        "last_name": unique_last,
        "gender": "male",
        "birth_date": "1975-09-01",
        "height_cm": 180.0,
        "weight_kg": 82.0,
    }
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            first = await client.post("/api/patients/manual-entry", json=payload)
            assert first.status_code == 201
            first_id = first.json()["patient_id"]
            assert first.json()["matched_existing_patient"] is False

            # same person, later visit --> new vitals, same natural key
            follow_up = dict(payload, weight_kg=84.0, systolic_bp=130, diastolic_bp=85)
            second = await client.post("/api/patients/manual-entry", json=follow_up)
            assert second.status_code == 201
            assert second.json()["matched_existing_patient"] is True
            assert second.json()["patient_id"] == first_id

@pytest.mark.anyio
async def test_manual_entry_defensive_null_bmi():
    payload = {
        "first_name": "NoWeight",
        "last_name": f"Case{uuid.uuid4().hex[:8]}",
        "birth_date": "2001-01-01",
        "height_cm": 170.0,
        # weight_kg omitted entirely
    }
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/patients/manual-entry", json=payload)
            assert response.status_code == 201
            data = response.json()
            assert data["bmi"] is None
            assert data["bmi_category"] is None
            assert data["observations_recorded"] == 1  # only height recorded

@pytest.mark.anyio
async def test_manual_entry_rejects_out_of_range_vitals():
    payload = {
        "first_name": "Bad",
        "last_name": f"Input{uuid.uuid4().hex[:8]}",
        "birth_date": "1990-01-01",
        "systolic_bp": 999,  # literally impossible
    }
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/patients/manual-entry", json=payload)
            assert response.status_code == 422
