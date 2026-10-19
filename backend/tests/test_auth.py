from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from joserfc import jwk, jwt
from pydantic import SecretStr
from sqlalchemy import Engine

from app.core.auth import SESSION_COOKIE, token_hash
from app.db.auth_repository import get_auth_repository
from app.main import create_app
from app.models import User


class MemoryAuthRepository:
    """Test double only; production always uses SQLAlchemy/PostgreSQL."""

    def __init__(self):
        self.users = {}
        self.sessions = {}
        self.commits = 0

    def upsert_user(self, email, name, avatar):
        user = next((u for u in self.users.values() if u.email.strip().lower() == email), None)
        if user is None:
            now = datetime.now(UTC)
            user = User(
                id=uuid4(),
                email=email,
                name=name,
                avatar_url=avatar,
                created_at=now,
                updated_at=now,
            )
            self.users[user.id] = user
        else:
            user.email = email
            if name is not None:
                user.name = name
            if avatar is not None:
                user.avatar_url = avatar
            user.updated_at = datetime.now(UTC)
        return user

    def add_session(self, session):
        session.id = uuid4()
        session.created_at = datetime.now(UTC)
        self.sessions[session.token_hash] = session

    def user_for_session(self, hashed_token, now):
        session = self.sessions.get(hashed_token)
        if session is None or session.expires_at <= now:
            return None
        return self.users.get(session.user_id)

    def delete_session(self, hashed_token):
        self.sessions.pop(hashed_token, None)

    def commit(self):
        self.commits += 1


class MockGoogle:
    def __init__(self, key):
        self.key = key
        self.nonce = None
        self.claims = {}
        self.token_calls = 0
        self.fail_token = False
        self.bad_signature = False

    def request(self, request):
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(
                200,
                json={
                    "issuer": "https://accounts.google.com",
                    "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
                    "token_endpoint": "https://oauth2.googleapis.com/token",
                    "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
                    "id_token_signing_alg_values_supported": ["RS256"],
                },
            )
        if request.url.path == "/oauth2/v3/certs":
            return httpx.Response(200, json={"keys": [self.key.as_dict(private=False)]})
        if request.url.path == "/token":
            self.token_calls += 1
            if self.fail_token:
                return httpx.Response(503, json={"error": "unavailable"})
            fields = parse_qs(request.content.decode())
            assert fields["grant_type"] == ["authorization_code"]
            assert len(fields["code_verifier"][0]) >= 43
            now = int(datetime.now(UTC).timestamp())
            claims = {
                "iss": "https://accounts.google.com",
                "sub": "test-google-subject",
                "aud": "test-web-client",
                "iat": now,
                "exp": now + 300,
                "nonce": self.nonce,
                "email": " Person@Example.Test ",
                "email_verified": True,
                "name": "Test Person",
                "picture": "https://example.test/avatar.png",
            }
            claims.update(self.claims)
            key = (
                jwk.generate_key("RSA", 2048, {"kid": "test-key"})
                if self.bad_signature
                else self.key
            )
            identity = jwt.encode({"alg": "RS256", "kid": "test-key"}, claims, key)
            return httpx.Response(
                200,
                json={
                    "access_token": "test-google-access-token",
                    "token_type": "Bearer",
                    "id_token": identity,
                    "expires_in": 300,
                },
            )
        raise AssertionError("Unexpected external request")


@pytest.fixture(scope="module")
def google_key():
    return jwk.generate_key("RSA", 2048, {"kid": "test-key"})


@pytest.fixture
def auth_setup(settings, google_key, monkeypatch, request):
    def forbidden_database(*args, **kwargs):
        raise AssertionError("Auth unit tests must never connect to Neon or another database")

    monkeypatch.setattr(Engine, "connect", forbidden_database)
    configuration = settings.model_copy(
        update={
            "session_cookie_secure": getattr(request, "param", False),
            "google_client_id": "test-web-client",
            "google_client_secret": SecretStr("test-client-secret"),
        }
    )
    application = create_app(configuration)
    repository = MemoryAuthRepository()
    application.dependency_overrides[get_auth_repository] = lambda: repository
    provider = MockGoogle(google_key)
    google = application.state.oauth.create_client("google")
    google.client_kwargs["transport"] = httpx.MockTransport(provider.request)
    base_url = "https://127.0.0.1:8000" if configuration.secure_cookies else "http://127.0.0.1:8000"
    with TestClient(application, base_url=base_url) as client:
        yield SimpleNamespace(
            client=client, repository=repository, provider=provider, settings=configuration
        )


def begin(setup):
    response = setup.client.get("/api/auth/google/login", follow_redirects=False)
    assert response.status_code == 302
    parameters = parse_qs(urlsplit(response.headers["location"]).query)
    setup.provider.nonce = parameters["nonce"][0]
    return response, parameters


def finish(setup):
    _, parameters = begin(setup)
    return setup.client.get(
        "/api/auth/google/callback",
        params={
            "code": "test-authorization-code",
            "state": parameters["state"][0],
        },
        follow_redirects=False,
    )


def test_google_login_redirect_and_state_cookie(auth_setup):
    response, parameters = begin(auth_setup)
    assert response.headers["location"].startswith("https://accounts.google.com/")
    assert parameters["response_type"] == ["code"]
    assert set(parameters["scope"][0].split()) == {"openid", "email", "profile"}
    assert parameters["state"][0]
    assert parameters["code_challenge_method"] == ["S256"]
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie
    assert "path=/api/auth/google" in cookie
    assert "max-age=600" in cookie
    assert "test-client-secret" not in response.text + response.headers["location"] + cookie
    assert not auth_setup.repository.sessions


def test_callback_creates_user_and_authenticated_cookie(auth_setup):
    response = finish(auth_setup)
    assert response.status_code == 303
    assert response.headers["location"] == auth_setup.settings.frontend_origin
    assert len(auth_setup.repository.users) == 1
    user = next(iter(auth_setup.repository.users.values()))
    assert user.email == "person@example.test"
    assert user.name == "Test Person"
    assert user.avatar_url == "https://example.test/avatar.png"
    cookie = next(
        c for c in response.headers.get_list("set-cookie") if c.startswith(SESSION_COOKIE)
    )
    assert (
        "httponly" in cookie.lower()
        and "samesite=lax" in cookie.lower()
        and "path=/" in cookie.lower()
    )
    assert "Secure" not in cookie and "Domain=" not in cookie
    assert response.headers["cache-control"] == "no-store"
    assert auth_setup.client.cookies.get("meetguide_oauth_state") is None
    me = auth_setup.client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["id"] == str(user.id)
    assert set(me.json()) == {"id", "email", "name", "avatar_url", "created_at", "updated_at"}
    assert me.headers["cache-control"] == "no-store"


def test_returning_user_keeps_id_updates_profile_and_rotates_session(auth_setup):
    assert finish(auth_setup).status_code == 303
    user = next(iter(auth_setup.repository.users.values()))
    original_id = user.id
    old_token = auth_setup.client.cookies.get(SESSION_COOKIE)
    auth_setup.provider.claims = {"name": "Updated Name", "picture": "https://example.test/new.png"}
    assert finish(auth_setup).status_code == 303
    assert len(auth_setup.repository.users) == 1
    assert user.id == original_id and user.name == "Updated Name"
    assert user.avatar_url == "https://example.test/new.png"
    assert token_hash(old_token) not in auth_setup.repository.sessions
    assert len(auth_setup.repository.sessions) == 1


def test_missing_profile_does_not_erase_returning_user_fields(auth_setup):
    assert finish(auth_setup).status_code == 303
    auth_setup.provider.claims = {"name": None, "picture": None}
    assert finish(auth_setup).status_code == 303
    user = next(iter(auth_setup.repository.users.values()))
    assert user.name == "Test Person" and user.avatar_url == "https://example.test/avatar.png"


@pytest.mark.parametrize("verified", [False, "true", None])
def test_unverified_google_email_rejected(auth_setup, verified):
    auth_setup.provider.claims["email_verified"] = verified
    assert finish(auth_setup).status_code == 403
    assert not auth_setup.repository.users
    assert not auth_setup.repository.sessions
    assert auth_setup.client.cookies.get(SESSION_COOKIE) is None


@pytest.mark.parametrize("state", [None, "incorrect-state"])
def test_missing_or_mismatched_state_rejected_before_token_exchange(auth_setup, state):
    begin(auth_setup)
    parameters = {"code": "test-code"}
    if state is not None:
        parameters["state"] = state
    response = auth_setup.client.get("/api/auth/google/callback", params=parameters)
    assert response.status_code == 400
    assert auth_setup.provider.token_calls == 0
    assert not auth_setup.repository.sessions


def test_callback_without_state_cookie_rejected(auth_setup):
    _, parameters = begin(auth_setup)
    auth_setup.client.cookies.clear()
    response = auth_setup.client.get(
        "/api/auth/google/callback",
        params={
            "code": "test-code",
            "state": parameters["state"][0],
        },
    )
    assert response.status_code == 400
    assert auth_setup.provider.token_calls == 0


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "wrong-client"},
        {"iss": "https://untrusted.example"},
        {"nonce": "wrong-nonce"},
        {"exp": 1},
        {"sub": ""},
    ],
)
def test_invalid_signed_google_claims_rejected(auth_setup, claims):
    auth_setup.provider.claims = claims
    assert finish(auth_setup).status_code in {401, 403}
    assert not auth_setup.repository.users and not auth_setup.repository.sessions


def test_invalid_google_signature_rejected(auth_setup):
    auth_setup.provider.bad_signature = True
    assert finish(auth_setup).status_code == 401
    assert not auth_setup.repository.sessions


def test_google_network_error_sanitized(auth_setup):
    auth_setup.provider.fail_token = True
    response = finish(auth_setup)
    assert response.status_code == 503
    assert response.json() == {"detail": "Google login is temporarily unavailable"}
    assert not auth_setup.repository.sessions


def test_unauthenticated_me(auth_setup):
    assert auth_setup.client.get("/api/auth/me").status_code == 401


def test_expired_session_rejected(auth_setup):
    assert finish(auth_setup).status_code == 303
    session = next(iter(auth_setup.repository.sessions.values()))
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert auth_setup.client.get("/api/auth/me").status_code == 401


def test_raw_token_never_stored_in_session(auth_setup):
    assert finish(auth_setup).status_code == 303
    raw_token = auth_setup.client.cookies.get(SESSION_COOKIE)
    assert len(raw_token) == 43
    row = next(iter(auth_setup.repository.sessions.values()))
    assert row.token_hash == token_hash(raw_token)
    assert row.token_hash != raw_token
    assert raw_token not in row.__dict__.values()
    assert set(row.__table__.columns.keys()) == {
        "id",
        "user_id",
        "token_hash",
        "expires_at",
        "created_at",
    }


def test_logout_revokes_session_and_clears_cookie(auth_setup):
    assert finish(auth_setup).status_code == 303
    raw_token = auth_setup.client.cookies.get(SESSION_COOKIE)
    response = auth_setup.client.post(
        "/api/auth/logout",
        headers={
            "Origin": auth_setup.settings.frontend_origin,
        },
    )
    assert response.status_code == 204
    assert not auth_setup.repository.sessions
    assert auth_setup.client.cookies.get(SESSION_COOKIE) is None
    assert "Max-Age=0" in response.headers["set-cookie"]
    auth_setup.client.cookies.set(SESSION_COOKIE, raw_token)
    assert auth_setup.client.get("/api/auth/me").status_code == 401


@pytest.mark.parametrize("origin", [None, "https://untrusted.example"])
def test_logout_requires_trusted_origin(auth_setup, origin):
    assert finish(auth_setup).status_code == 303
    headers = {"Origin": origin} if origin else {}
    assert auth_setup.client.post("/api/auth/logout", headers=headers).status_code == 403
    assert auth_setup.repository.sessions


def test_logout_without_session_is_idempotent(auth_setup):
    response = auth_setup.client.post(
        "/api/auth/logout",
        headers={
            "Origin": auth_setup.settings.frontend_origin,
        },
    )
    assert response.status_code == 204


def test_unconfigured_google_login_returns_503(client):
    assert client.get("/api/auth/google/login").status_code == 503


@pytest.mark.parametrize("auth_setup", [True], indirect=True)
def test_authenticated_cookie_is_secure_when_configured(auth_setup):
    response = finish(auth_setup)
    assert response.status_code == 303
    cookie = next(
        c for c in response.headers.get_list("set-cookie") if c.startswith(SESSION_COOKIE)
    )
    assert "; secure" in cookie.lower()
    assert auth_setup.client.get("/api/auth/me").status_code == 200


def test_tampered_state_cookie_rejected(auth_setup):
    _, parameters = begin(auth_setup)
    for cookie in auth_setup.client.cookies.jar:
        if cookie.name == "meetguide_oauth_state":
            cookie.value = "invalid-signature"
    response = auth_setup.client.get(
        "/api/auth/google/callback",
        params={
            "code": "test-code",
            "state": parameters["state"][0],
        },
    )
    assert response.status_code == 400
    assert auth_setup.provider.token_calls == 0


def test_completed_flow_cannot_be_replayed_without_state(auth_setup):
    _, parameters = begin(auth_setup)
    query = {"code": "test-code", "state": parameters["state"][0]}
    assert (
        auth_setup.client.get(
            "/api/auth/google/callback", params=query, follow_redirects=False
        ).status_code
        == 303
    )
    assert (
        auth_setup.client.get(
            "/api/auth/google/callback", params=query, follow_redirects=False
        ).status_code
        == 400
    )
    assert auth_setup.provider.token_calls == 1


def test_database_failure_does_not_issue_cookie(auth_setup, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    def fail_commit():
        raise SQLAlchemyError("private database failure details")

    monkeypatch.setattr(auth_setup.repository, "commit", fail_commit)
    response = finish(auth_setup)
    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication is temporarily unavailable"}
    assert auth_setup.client.cookies.get(SESSION_COOKIE) is None
