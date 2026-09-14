import os, pytest, uuid
from httpx import ASGITransport, AsyncClient
from api.main import app, lifespan

# Must match a real API_KEY in the environment (set in .env locally, in
# ci.yml in CI) since api.main reads it once at import time.
AUTH_HEADERS = {"X-API-Key": os.getenv("API_KEY", "test-key")}

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
            response = await client.post("/api/patients/ingest", json=valid_payload, headers=AUTH_HEADERS)
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
            response = await client.post("/api/patients/ingest", json=invalid_payload, headers=AUTH_HEADERS)
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
            response = await client.post("/api/patients/manual-entry", json=payload, headers=AUTH_HEADERS)
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
            first = await client.post("/api/patients/manual-entry", json=payload, headers=AUTH_HEADERS)
            assert first.status_code == 201
            first_id = first.json()["patient_id"]
            assert first.json()["matched_existing_patient"] is False

            # same person, later visit --> new vitals, same natural key
            follow_up = dict(payload, weight_kg=84.0, systolic_bp=130, diastolic_bp=85)
            second = await client.post("/api/patients/manual-entry", json=follow_up, headers=AUTH_HEADERS)
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
            response = await client.post("/api/patients/manual-entry", json=payload, headers=AUTH_HEADERS)
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
            response = await client.post("/api/patients/manual-entry", json=payload, headers=AUTH_HEADERS)
            assert response.status_code == 422

@pytest.mark.anyio
async def test_lookup_finds_existing_match():
    unique_last = f"Lookupfound{uuid.uuid4().hex[:8]}"
    payload = {
        "first_name": "Lucy",
        "last_name": unique_last,
        "birth_date": "1985-03-20",
        "height_cm": 162.0,
        "weight_kg": 58.0,
    }
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post("/api/patients/manual-entry", json=payload, headers=AUTH_HEADERS)
            assert created.status_code == 201
            patient_id = created.json()["patient_id"]

            response = await client.get(
                "/api/patients/lookup",
                params={
                    "first_name": "Lucy",
                    "last_name": unique_last,
                    "birth_date": "1985-03-20",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["match_found"] is True
            assert data["patient"]["id"] == patient_id
            assert data["patient"]["first_name"] == "Lucy"
            assert data["patient"]["bmi"] == created.json()["bmi"]

@pytest.mark.anyio
async def test_lookup_returns_no_match_for_unknown_patient():
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/patients/lookup",
                params={
                    "first_name": "Nobody",
                    "last_name": f"Exists{uuid.uuid4().hex[:8]}",
                    "birth_date": "1970-01-01",
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["match_found"] is False
            assert data["patient"] is None

@pytest.mark.anyio
async def test_manual_entry_force_new_creates_second_patient_despite_matching_name_dob():
    unique_last = f"Sameperson{uuid.uuid4().hex[:8]}"
    payload = {
        "first_name": "Alex",
        "last_name": unique_last,
        "birth_date": "1990-01-01",
        "height_cm": 175.0,
        "weight_kg": 70.0,
    }
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            first = await client.post("/api/patients/manual-entry", json=payload, headers=AUTH_HEADERS)
            assert first.status_code == 201
            first_id = first.json()["patient_id"]

            # Same name + DOB, but the DOCTOR confirms it's a different person.
            second = await client.post(
                "/api/patients/manual-entry",
                json={**payload, "force_new": True},
                headers=AUTH_HEADERS,
            )
            assert second.status_code == 201
            assert second.json()["matched_existing_patient"] is False
            assert second.json()["patient_id"] != first_id

@pytest.mark.anyio
async def test_get_patient_observations_returns_full_history_oldest_first():
    unique_last = f"History{uuid.uuid4().hex[:8]}"
    first_visit = {
        "first_name": "Morgan",
        "last_name": unique_last,
        "birth_date": "1992-07-04",
        "height_cm": 170.0,
        "weight_kg": 65.0,
        "observation_date": "2024-01-10",
    }
    second_visit = dict(first_visit, weight_kg=67.0, observation_date="2024-06-15")

    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            first = await client.post("/api/patients/manual-entry", json=first_visit, headers=AUTH_HEADERS)
            assert first.status_code == 201
            patient_id = first.json()["patient_id"]

            second = await client.post("/api/patients/manual-entry", json=second_visit, headers=AUTH_HEADERS)
            assert second.status_code == 201
            assert second.json()["patient_id"] == patient_id  # same natural key, same patient

            response = await client.get(f"/api/patients/{patient_id}/observations")
            assert response.status_code == 200
            rows = response.json()

            weight_rows = [r for r in rows if r["observation_code"] == "29463-7"]
            assert [r["observation_value"] for r in weight_rows] == [65.0, 67.0]
            assert weight_rows[0]["observation_date"] < weight_rows[1]["observation_date"]

@pytest.mark.anyio
async def test_get_patient_by_id_returns_snapshot():
    unique_last = f"Byid{uuid.uuid4().hex[:8]}"
    payload = {
        "first_name": "Priya",
        "last_name": unique_last,
        "birth_date": "1994-11-02",
        "height_cm": 160.0,
        "weight_kg": 55.0,
    }
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post("/api/patients/manual-entry", json=payload, headers=AUTH_HEADERS)
            assert created.status_code == 201
            patient_id = created.json()["patient_id"]

            response = await client.get(f"/api/patients/{patient_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == patient_id
            assert data["first_name"] == "Priya"
            assert data["bmi"] == created.json()["bmi"]

@pytest.mark.anyio
async def test_get_patient_by_id_404_for_unknown_id():
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(f"/api/patients/{uuid.uuid4()}")
            assert response.status_code == 404


@pytest.mark.anyio
async def test_manual_entry_requires_api_key():
    payload = {
        "first_name": "NoKey",
        "last_name": f"Case{uuid.uuid4().hex[:8]}",
        "birth_date": "1990-01-01",
    }
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/patients/manual-entry", json=payload)
            assert response.status_code == 401

@pytest.mark.anyio
async def test_manual_entry_rejects_wrong_api_key():
    payload = {
        "first_name": "WrongKey",
        "last_name": f"Case{uuid.uuid4().hex[:8]}",
        "birth_date": "1990-01-01",
    }
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/patients/manual-entry",
                json=payload,
                headers={"X-API-Key": "definitely-not-it"},
            )
            assert response.status_code == 401

@pytest.mark.anyio
async def test_ingest_requires_api_key():
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/patients/ingest", json={"resourceType": "Bundle"})
            assert response.status_code == 401

@pytest.mark.anyio
async def test_stats_endpoint_shape():
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/stats")
            assert response.status_code == 200
            data = response.json()
            assert "total_patients" in data
            assert data["total_patients"] >= 0
            assert "bmi_distribution" in data
            for key in ("underweight", "normal", "overweight", "obese"):
                assert key in data["bmi_distribution"]

@pytest.mark.anyio
async def test_stats_reflects_a_freshly_created_patient():
    # /api/stats is a SQL-side COUNT(*), not "however many rows a paginated
    # /api/patients call happened to return" -- this is the regression test
    # for that distinction: create a patient, then confirm the total went up
    # by exactly one rather than being silently capped at a page size.
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            before = (await client.get("/api/stats")).json()["total_patients"]
            await client.post(
                "/api/patients/manual-entry",
                json={
                    "first_name": f"StatsCheck{uuid.uuid4().hex[:8]}",
                    "last_name": "Patient",
                    "birth_date": "1988-04-04",
                    "height_cm": 170,
                    "weight_kg": 70,
                },
                headers=AUTH_HEADERS,
            )
            after = (await client.get("/api/stats")).json()["total_patients"]
            assert after == before + 1

@pytest.mark.anyio
async def test_recent_activity_respects_limit():
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/patients/recent-activity?limit=3")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) <= 3

@pytest.mark.anyio
async def test_recent_activity_includes_a_freshly_recorded_visit():
    async with lifespan(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            unique_last_name = f"Activity{uuid.uuid4().hex[:8]}"
            await client.post(
                "/api/patients/manual-entry",
                json={
                    "first_name": "Recent",
                    "last_name": unique_last_name,
                    "birth_date": "1979-02-02",
                    "height_cm": 168,
                    "weight_kg": 64,
                },
                headers=AUTH_HEADERS,
            )
            response = await client.get("/api/patients/recent-activity?limit=10")
            assert response.status_code == 200
            last_names = [entry["last_name"] for entry in response.json()]
            # The API title-cases names on intake (ManualPatientIntake normalizes
            # this so name matching isn't case-sensitive) -- Python's .title()
            # also capitalizes any letter right after a digit, so a hex-suffixed
            # test name like "Activity7b3a727e" comes back "Activity7B3A727E".
            # Assert against what the app actually, correctly, stores.
            assert unique_last_name.title() in last_names
