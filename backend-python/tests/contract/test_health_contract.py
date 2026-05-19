from fastapi.testclient import TestClient

from app.main import create_app


def test_api_health_contract_uses_unified_response() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health", headers={"X-Trace-Id": "stage1-trace"})

    assert response.status_code == 200
    assert response.headers["X-Trace-Id"] == "stage1-trace"
    body = response.json()
    assert body["success"] is True
    assert body["code"] == "OK"
    assert body["message"] == "success"
    assert body["traceId"] == "stage1-trace"
    assert body["data"]["status"] == "UP"
    assert body["data"]["application"] == "ai-code-review-platform"
    assert body["data"]["time"]


def test_actuator_health_contract_is_spring_compatible() -> None:
    client = TestClient(create_app())

    response = client.get("/actuator/health")

    assert response.status_code == 200
    assert response.json() == {"status": "UP"}
    assert response.headers["X-Trace-Id"]


def test_not_found_uses_unified_error_response() -> None:
    client = TestClient(create_app())

    response = client.get("/api/not-exists")

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["code"] == "RESOURCE_NOT_FOUND"
    assert body["message"] == "Resource not found"
    assert body["data"] is None
    assert body["traceId"]

