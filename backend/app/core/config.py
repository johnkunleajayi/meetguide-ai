from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
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

    google_client_id: str | None = Field(default=None, repr=False)
    google_client_secret: SecretStr | None = Field(default=None, repr=False)
    google_redirect_uri: str = "http://127.0.0.1:8000/api/auth/google/callback"
    auth_state_secret: SecretStr | None = Field(default=None, repr=False)
    session_cookie_secure: bool | None = None
    session_ttl_seconds: int = Field(default=604800, ge=60, le=2592000)

    @field_validator("auth_state_secret")
    @classmethod
    def validate_state_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value()) < 32:
            raise ValueError("AUTH_STATE_SECRET must contain at least 32 characters")
        return value

    @field_validator("google_redirect_uri")
    @classmethod
    def validate_redirect_uri(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path != "/api/auth/google/callback"
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("GOOGLE_REDIRECT_URI must be an HTTP(S) Google callback URL")
        return value

    @model_validator(mode="after")
    def validate_cookie_security(self) -> "Settings":
        if not self.secure_cookies:
            origins = [self.frontend_origin, self.desktop_origin, self.google_redirect_uri]
            if self.app_env == "production" or any(
                urlsplit(origin).hostname not in {"localhost", "127.0.0.1", "::1"}
                for origin in origins
            ):
                raise ValueError(
                    "Insecure cookies are allowed only for loopback development/testing"
                )
        if self.app_env == "production" and self.google_client_id:
            if self.auth_state_secret is None:
                raise ValueError("AUTH_STATE_SECRET is required for production Google login")
            if urlsplit(self.google_redirect_uri).scheme != "https":
                raise ValueError("Production Google callback must use HTTPS")
        return self

    @property
    def secure_cookies(self) -> bool:
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.app_env == "production"

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
