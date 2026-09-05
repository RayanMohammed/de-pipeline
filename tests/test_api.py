import pytest
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