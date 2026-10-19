from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

    app_name: str = Field(default="MeetGuide AI API", min_length=1)
    app_env: Literal["development", "test", "production"] = "development"
    database_url: SecretStr
    frontend_origin: str = "http://127.0.0.1:5173"
    desktop_origin: str = "http://127.0.0.1:1420"

    @field_validator("database_url")
    @classmethod
    def require_postgresql(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
        except (ArgumentError, ValueError) as exc:
            raise ValueError("DATABASE_URL must be a valid PostgreSQL URL") from exc
        if url.drivername != "postgresql+psycopg" or not url.host or not url.database:
            raise ValueError("DATABASE_URL must use postgresql+psycopg with a host and database")
        return value

    @field_validator("frontend_origin", "desktop_origin")
    @classmethod
    def validate_origin(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("Origin must be a valid HTTP(S) origin") from exc
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or "*" in value
            or "<" in value
            or ">" in value
            or any(character.isspace() for character in value)
        ):
            raise ValueError("Origin must be an exact HTTP(S) origin without credentials or a path")
        # Read the port property above to reject malformed port values.
        if port is not None and port == 0:
            raise ValueError("Origin port must be nonzero")
        return value.rstrip("/")

    @property
    def cors_origins(self) -> list[str]:
        return list(dict.fromkeys([self.frontend_origin, self.desktop_origin]))


@lru_cache
def get_settings() -> Settings:
    return Settings()
