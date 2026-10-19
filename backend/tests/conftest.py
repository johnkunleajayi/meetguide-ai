from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.core.config import Settings, get_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for name in (
        "APP_NAME",
        "APP_ENV",
        "DATABASE_URL",
        "FRONTEND_ORIGIN",
        "DESKTOP_ORIGIN",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "GOOGLE_REDIRECT_URI",
        "AUTH_STATE_SECRET",
        "SESSION_COOKIE_SECURE",
        "SESSION_TTL_SECONDS",
        "CONTEXT_STORAGE_DIR",
        "TRANSCRIPTION_PROVIDER",
        "DEEPGRAM_API_KEY",
        "TRANSCRIPTION_MODEL",
        "TRANSCRIPTION_LANGUAGE",
    ):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_name="MeetGuide AI API",
        app_env="test",
        database_url="postgresql+psycopg://127.0.0.1:1/meetguide_test",
        frontend_origin="http://127.0.0.1:5173",
        desktop_origin="http://127.0.0.1:1420",
    )


@pytest.fixture
def client(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    def forbidden_connection(*args: object, **kwargs: object) -> None:
        raise AssertionError("Health/startup tests must not connect to PostgreSQL")

    monkeypatch.setattr(Engine, "connect", forbidden_connection)
    with TestClient(create_app(settings)) as test_client:
        yield test_client
