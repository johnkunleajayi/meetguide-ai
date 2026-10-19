from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.core.config import Settings
from app.main import create_app


def test_application_startup_without_database(client: TestClient) -> None:
    assert client.app.state.settings.app_env == "test"
    assert client.app.state.engine.url.drivername == "postgresql+psycopg"
    assert client.app.state.session_factory.kw["bind"] is client.app.state.engine
    assert client.app.state.engine.pool.checkedout() == 0


def test_health_returns_expected_response(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "MeetGuide AI API"}
    assert response.headers["content-type"] == "application/json"


def test_swagger_and_openapi_available(client: TestClient) -> None:
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "swagger-ui" in docs.text
    schema = client.get("/openapi.json")
    assert schema.status_code == 200
    assert "/api/health" in schema.json()["paths"]


@pytest.mark.parametrize("origin", ["http://127.0.0.1:5173", "http://127.0.0.1:1420"])
def test_allowed_client_origins(client: TestClient, origin: str) -> None:
    response = client.options(
        "/api/health",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


def test_unconfigured_origin_rejected(client: TestClient) -> None:
    response = client.options(
        "/api/health",
        headers={
            "Origin": "https://untrusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_engine_disposed_on_shutdown(settings: Settings) -> None:
    with patch.object(Engine, "dispose", autospec=True) as dispose:
        with TestClient(create_app(settings)) as client:
            engine = client.app.state.engine
            dispose.assert_not_called()
        dispose.assert_called_once_with(engine)
