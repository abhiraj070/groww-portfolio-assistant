from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.security import require_api_key
from app.main import create_app

TEST_KEY = "synthetic-local-service-key-for-tests-only"


def app_with_private_probe() -> FastAPI:
    application = create_app()

    @application.get("/private-probe", dependencies=[Depends(require_api_key)])
    def private_probe():
        return {"ok": True}

    return application


def test_health_without_credentials():
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "mode": "read_only"}


def test_private_route_fails_closed_without_configuration():
    with TestClient(app_with_private_probe()) as client:
        response = client.get("/private-probe")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "http_503"


def test_private_route_authentication(monkeypatch):
    monkeypatch.setenv("SERVICE_API_KEY", TEST_KEY)
    with TestClient(app_with_private_probe()) as client:
        for headers in ({}, {"X-API-Key": "wrong"}):
            response = client.get("/private-probe", headers=headers)
            assert response.status_code == 401
            assert TEST_KEY not in response.text
        response = client.get("/private-probe", headers={"X-API-Key": TEST_KEY})
    assert response.status_code == 200


def test_unimplemented_routes_return_404():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/portfolio/holdings")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "http_404", "message": "Resource not found"}}


def test_errors_do_not_expose_exception_details():
    application = create_app()

    @application.get("/failure")
    def failure():
        raise RuntimeError("synthetic-sensitive-detail")

    @application.get("/http-failure")
    def http_failure():
        raise HTTPException(400, detail="synthetic-sensitive-detail")

    with TestClient(application, raise_server_exceptions=False) as client:
        for path, status in (("/failure", 500), ("/http-failure", 400)):
            response = client.get(path)
            assert response.status_code == status
            assert "synthetic-sensitive-detail" not in response.text
