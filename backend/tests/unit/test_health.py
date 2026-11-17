from fastapi.testclient import TestClient

from invoiceguard.api import health
from invoiceguard.api.main import app

client = TestClient(app)


def test_health_ok_when_all_checks_pass(monkeypatch):
    monkeypatch.setattr(health, "check_postgres", lambda: "ok")
    monkeypatch.setattr(health, "check_redis", lambda: "ok")

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"postgres": "ok", "redis": "ok"}}


def test_health_degraded_when_a_dependency_fails(monkeypatch):
    monkeypatch.setattr(health, "check_postgres", lambda: "ok")
    monkeypatch.setattr(health, "check_redis", lambda: "error: ConnectionError")

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"]["redis"] == "error: ConnectionError"
