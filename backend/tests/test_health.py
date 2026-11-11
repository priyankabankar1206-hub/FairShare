"""Tests for health check endpoints and API documentation."""

def test_root_health_endpoint(client):
    """Test top-level /health endpoint returns 200 OK and valid schema."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["app_name"] == "FairShare Backend"
    assert data["version"] == "0.1.0"
    assert data["database_status"] == "pending_database_team"


def test_api_v1_health_endpoint(client):
    """Test /api/v1/health endpoint returns 200 OK."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_openapi_docs_accessible(client):
    """Test OpenAPI schema and Swagger UI are accessible."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "paths" in schema
    assert "/health" in schema["paths"]
    assert "/api/v1/health" in schema["paths"]
    assert "/api/v1/teams/{team_id}/scores" in schema["paths"]
