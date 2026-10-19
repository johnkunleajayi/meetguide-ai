import hashlib
import re
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from app.core.config import Settings
from app.db.auth_repository import AuthRepository
from app.models import Session, User

SESSION_COOKIE = "meetguide_session"
TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_-]{43}\Z")


class InvalidIdentity(ValueError):
    pass


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def valid_token(token: str | None) -> bool:
    return token is not None and TOKEN_PATTERN.fullmatch(token) is not None


def profile_fields(claims: dict) -> tuple[str, str | None, str | None]:
    email = claims.get("email")
    if claims.get("email_verified") is not True or not isinstance(email, str):
        raise InvalidIdentity("A verified Google email is required")
    email = email.strip().lower()
    if (
        not email
        or len(email) > 320
        or email.count("@") != 1
        or not all(email.split("@"))
        or any(character.isspace() for character in email)
        or not isinstance(claims.get("sub"), str)
        or not claims["sub"]
    ):
        raise InvalidIdentity("A valid Google identity is required")
    name = claims.get("name")
    name = name.strip() if isinstance(name, str) else None
    if not name or len(name) > 255:
        name = None
    avatar = claims.get("picture")
    if not isinstance(avatar, str) or len(avatar) > 4096:
        avatar = None
    else:
        try:
            parsed_avatar = urlsplit(avatar)
            if parsed_avatar.scheme != "https" or not parsed_avatar.hostname:
                avatar = None
        except ValueError:
            avatar = None
    return email, name, avatar


def complete_login(
    repository: AuthRepository, claims: dict, settings: Settings, old_token: str | None
) -> tuple[User, str]:
    email, name, avatar = profile_fields(claims)
    user = repository.upsert_user(email, name, avatar)
    raw_token = secrets.token_urlsafe(32)
    repository.add_session(
        Session(
            user_id=user.id,
            token_hash=token_hash(raw_token),
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    if valid_token(old_token):
        repository.delete_session(token_hash(old_token))
    repository.commit()
    return user, raw_token


def authenticated_user(repository: AuthRepository, raw_token: str | None) -> User | None:
    if not valid_token(raw_token):
        return None
    return repository.user_for_session(token_hash(raw_token), datetime.now(UTC))


def logout(repository: AuthRepository, raw_token: str | None) -> None:
    if valid_token(raw_token):
        repository.delete_session(token_hash(raw_token))
        repository.commit()
