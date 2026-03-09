from fastapi.testclient import TestClient

from app.main import app


def test_health_check():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_swagger_docs():
    client = TestClient(app)
    response = client.get("/docs")
    assert response.status_code == 200
