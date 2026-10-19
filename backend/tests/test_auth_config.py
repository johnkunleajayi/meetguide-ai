import pytest
from pydantic import SecretStr, ValidationError
from starlette.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_production_enforces_secure_cookies_and_stable_oauth_key():
    values = {
        "_env_file": None,
        "database_url": "postgresql+psycopg://example.invalid/test",
        "app_env": "production",
        "google_client_id": "test-client",
        "google_client_secret": "test-secret",
        "google_redirect_uri": "https://api.example.test/api/auth/google/callback",
    }
    with pytest.raises(ValidationError):
        Settings(**values)
    values["auth_state_secret"] = "test-only-state-signing-secret-not-real-credentials"
    settings = Settings(**values)
    assert settings.secure_cookies
    with pytest.raises(ValidationError):
        Settings(**values, session_cookie_secure=False)


def test_remote_origins_cannot_use_insecure_cookies():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://example.invalid/test",
            frontend_origin="https://web.example.test",
            session_cookie_secure=False,
        )


def test_production_login_state_cookie_is_secure(settings, monkeypatch):
    configuration = settings.model_copy(
        update={
            "app_env": "production",
            "session_cookie_secure": True,
            "auth_state_secret": SecretStr("test-only-state-signing-secret-not-real-credentials"),
            "google_client_id": "test-client",
            "google_client_secret": SecretStr("test-secret"),
            "google_redirect_uri": "https://api.example.test/api/auth/google/callback",
        }
    )
    application = create_app(configuration)
    google = application.state.oauth.create_client("google")
    google.server_metadata.update(
        {
            "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
            "_loaded_at": 1,
        }
    )
    with TestClient(application, base_url="https://api.example.test") as client:
        response = client.get("/api/auth/google/login", follow_redirects=False)
        assert response.status_code == 302
        assert "; secure" in response.headers["set-cookie"].lower()
