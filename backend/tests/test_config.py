import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings

TEST_DATABASE_URL = "postgresql+psycopg://example.invalid/meetguide_test"


def test_configuration_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "MeetGuide AI API")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    monkeypatch.setenv("FRONTEND_ORIGIN", "http://localhost:5173")
    monkeypatch.setenv("DESKTOP_ORIGIN", "http://localhost:1420")
    settings = Settings(_env_file=None)
    assert settings.app_name == "MeetGuide AI API"
    assert settings.app_env == "test"
    assert settings.database_url.get_secret_value() == TEST_DATABASE_URL
    assert settings.cors_origins == ["http://localhost:5173", "http://localhost:1420"]


def test_dotenv_and_environment_precedence(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        f'DATABASE_URL="{TEST_DATABASE_URL}"\nAPP_NAME="From file"\nAPP_ENV="test"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("APP_NAME", "From environment")
    settings = Settings(_env_file=dotenv)
    assert settings.app_name == "From environment"
    assert settings.database_url.get_secret_value() == TEST_DATABASE_URL


def test_database_url_is_required() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "url",
    ["sqlite:///example.db", "postgresql+psycopg2://example.invalid/db", "not-a-url"],
)
def test_non_psycopg_database_urls_rejected(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=url)


def test_database_credentials_hidden() -> None:
    # Explicit placeholders, not usable credentials.
    url = "postgresql+psycopg://placeholder-user:placeholder-password@example.invalid/test"
    settings = Settings(_env_file=None, database_url=url)
    assert "placeholder-password" not in repr(settings)
    assert "placeholder-password" not in settings.model_dump_json()


@pytest.mark.parametrize("origin", ["*", "https://example.com/path", "https://u:p@example.com"])
def test_unsafe_origins_rejected(origin: str) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=TEST_DATABASE_URL, frontend_origin=origin)


def test_unknown_environment_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url=TEST_DATABASE_URL, app_env="unknown")


def test_get_settings_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    first = get_settings()
    assert get_settings() is first
