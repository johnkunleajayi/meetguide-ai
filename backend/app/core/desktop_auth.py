"""Single-use, PKCE-bound desktop handoffs using the existing sessions table."""

import base64
import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from app.core import auth
from app.core.config import Settings
from app.db.auth_repository import AuthRepository
from app.models import Session

HANDOFF_TTL_SECONDS = 60


def challenge(verifier: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode()
    )


def handoff_hash(code: str) -> str:
    # A handoff can never be used as an ordinary session credential.
    return auth.token_hash("desktop-handoff:" + code)


def create_handoff(repository: AuthRepository, claims: dict, code_challenge: str) -> str:
    email, name, avatar = auth.profile_fields(claims)
    user = repository.upsert_user(email, name, avatar)
    code = secrets.token_urlsafe(32) + "." + code_challenge
    repository.add_session(
        Session(
            user_id=user.id,
            token_hash=handoff_hash(code),
            expires_at=datetime.now(UTC) + timedelta(seconds=HANDOFF_TTL_SECONDS),
        )
    )
    repository.commit()
    return code


def exchange_handoff(
    repository: AuthRepository, code: str, verifier: str, settings: Settings
) -> str | None:
    parts = code.split(".")
    if (
        len(parts) != 2
        or not all(auth.valid_token(part) for part in parts)
        or not auth.valid_token(verifier)
        or not secrets.compare_digest(parts[1], challenge(verifier))
    ):
        return None
    # PostgreSQL DELETE ... RETURNING atomically consumes the code across workers.
    user_id = repository.consume_handoff(handoff_hash(code), datetime.now(UTC))
    if user_id is None:
        return None
    token = secrets.token_urlsafe(32)
    repository.add_session(
        Session(
            user_id=user_id,
            token_hash=auth.token_hash(token),
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
        )
    )
    repository.commit()
    return token
