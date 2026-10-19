from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from sqlalchemy.dialects import postgresql

from app.core import auth, desktop_auth
from app.db.auth_repository import AuthRepository
from tests.test_auth import auth_setup as _auth_setup
from tests.test_auth import finish
from tests.test_auth import google_key as _google_key

auth_setup = _auth_setup
google_key = _google_key

VERIFIER = "v" * 43
STATE = "s" * 43


def desktop_finish(setup, **changes):
    params = {
        "desktop_port": "49152",
        "desktop_state": STATE,
        "code_challenge": desktop_auth.challenge(VERIFIER),
        **changes,
    }
    response = setup.client.get("/api/auth/google/login", params=params, follow_redirects=False)
    assert response.status_code == 302
    oauth = parse_qs(urlsplit(response.headers["location"]).query)
    setup.provider.nonce = oauth["nonce"][0]
    return setup.client.get(
        "/api/auth/google/callback",
        params={"code": "test-code", "state": oauth["state"][0]},
        follow_redirects=False,
    )


def handoff(setup):
    response = desktop_finish(setup)
    assert response.status_code == 303
    redirect = urlsplit(response.headers["location"])
    assert redirect.scheme == "http" and redirect.netloc == "127.0.0.1:49152"
    assert redirect.path == "/callback"
    params = parse_qs(redirect.query)
    assert params["state"] == [STATE]
    assert setup.client.cookies.get(auth.SESSION_COOKIE) is None
    assert response.headers["referrer-policy"] == "no-referrer"
    return params["code"][0]


def exchange(setup, code, verifier=VERIFIER):
    return setup.client.post(
        "/api/auth/desktop/exchange", json={"code": code, "verifier": verifier}
    )


def add_consumption(repository):
    def consume(hashed, now):
        row = repository.sessions.get(hashed)
        if row is None or row.expires_at <= now:
            return None
        repository.sessions.pop(hashed)
        return row.user_id

    repository.consume_handoff = consume


@pytest.fixture(autouse=True)
def memory_consumption(auth_setup):
    add_consumption(auth_setup.repository)


def test_desktop_login_exchange_user_and_logout(auth_setup):
    code = handoff(auth_setup)
    row = next(iter(auth_setup.repository.sessions.values()))
    assert row.token_hash == desktop_auth.handoff_hash(code)
    assert row.token_hash != code
    assert not auth.valid_token(code)
    result = exchange(auth_setup, code)
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    token = result.json()["session_token"]
    assert auth.valid_token(token)
    assert list(auth_setup.repository.sessions) == [auth.token_hash(token)]
    headers = {"Authorization": f"Bearer {token}"}
    me = auth_setup.client.get("/api/auth/desktop/me", headers=headers)
    assert me.status_code == 200 and me.json()["email"] == "person@example.test"
    assert auth_setup.client.get("/api/auth/me").status_code == 401
    assert auth_setup.client.post("/api/auth/desktop/logout", headers=headers).status_code == 204
    assert auth_setup.client.get("/api/auth/desktop/me", headers=headers).status_code == 401
    assert not auth_setup.repository.sessions


def test_handoff_is_single_use_and_pkce_bound(auth_setup):
    code = handoff(auth_setup)
    assert exchange(auth_setup, code, "w" * 43).status_code == 401
    assert exchange(auth_setup, code).status_code == 200
    assert exchange(auth_setup, code).status_code == 401


def test_tampered_challenge_cannot_redeem(auth_setup):
    code = handoff(auth_setup)
    other = code.split(".")[0] + "." + desktop_auth.challenge("w" * 43)
    assert exchange(auth_setup, other, "w" * 43).status_code == 401
    assert exchange(auth_setup, code).status_code == 200


def test_expired_handoff_cannot_be_exchanged(auth_setup):
    code = handoff(auth_setup)
    next(iter(auth_setup.repository.sessions.values())).expires_at = datetime.now(UTC) - timedelta(
        seconds=1
    )
    assert exchange(auth_setup, code).status_code == 401


def test_handoff_is_not_accepted_as_a_native_session(auth_setup):
    code = handoff(auth_setup)
    assert (
        auth_setup.client.get(
            "/api/auth/desktop/me", headers={"Authorization": f"Bearer {code}"}
        ).status_code
        == 401
    )


def test_native_session_expiry(auth_setup):
    result = exchange(auth_setup, handoff(auth_setup))
    token = result.json()["session_token"]
    next(iter(auth_setup.repository.sessions.values())).expires_at = datetime.now(UTC) - timedelta(
        seconds=1
    )
    assert (
        auth_setup.client.get(
            "/api/auth/desktop/me", headers={"Authorization": f"Bearer {token}"}
        ).status_code
        == 401
    )


def test_desktop_reuses_web_user_without_revoking_web_session(auth_setup):
    assert finish(auth_setup).status_code == 303
    web_token = auth_setup.client.cookies.get(auth.SESSION_COOKIE)
    web_user = auth_setup.client.get("/api/auth/me").json()["id"]
    response = desktop_finish(auth_setup)
    code = parse_qs(urlsplit(response.headers["location"]).query)["code"][0]
    assert exchange(auth_setup, code).status_code == 200
    assert len(auth_setup.repository.users) == 1
    assert auth_setup.client.cookies.get(auth.SESSION_COOKIE) == web_token
    assert auth_setup.client.get("/api/auth/me").json()["id"] == web_user
    assert len(auth_setup.repository.sessions) == 2


def test_native_routes_never_fall_back_to_browser_cookie(auth_setup):
    assert finish(auth_setup).status_code == 303
    assert auth_setup.client.get("/api/auth/desktop/me").status_code == 401
    assert auth_setup.client.post("/api/auth/desktop/logout").status_code == 401
    assert auth_setup.client.get("/api/auth/me").status_code == 200


def test_unverified_identity_does_not_issue_handoff(auth_setup):
    auth_setup.provider.claims["email_verified"] = False
    assert desktop_finish(auth_setup).status_code == 403
    assert not auth_setup.repository.sessions


def test_desktop_flow_rejects_invalid_google_state(auth_setup):
    auth_setup.client.get(
        "/api/auth/google/login",
        params={
            "desktop_port": 49152,
            "desktop_state": STATE,
            "code_challenge": desktop_auth.challenge(VERIFIER),
        },
    )
    response = auth_setup.client.get(
        "/api/auth/google/callback", params={"state": "wrong", "code": "test"}
    )
    assert response.status_code == 400
    assert not auth_setup.repository.sessions


@pytest.mark.parametrize(
    "params",
    [
        {"desktop_port": "80"},
        {"desktop_port": "65536"},
        {"desktop_port": "evil.test"},
        {"desktop_state": "bad"},
        {"code_challenge": "bad"},
        {"desktop_port": "1" * 5000},
    ],
)
def test_invalid_desktop_parameters_rejected(auth_setup, params):
    query = {
        "desktop_port": "49152",
        "desktop_state": STATE,
        "code_challenge": desktop_auth.challenge(VERIFIER),
        **params,
    }
    response = auth_setup.client.get("/api/auth/google/login", params=query)
    assert response.status_code == 400
    assert auth_setup.provider.token_calls == 0


def test_partial_or_duplicate_desktop_parameters_rejected(auth_setup):
    assert auth_setup.client.get("/api/auth/google/login?desktop_port=49152").status_code == 400
    params = [
        ("desktop_port", "49152"),
        ("desktop_port", "49153"),
        ("desktop_state", STATE),
        ("code_challenge", desktop_auth.challenge(VERIFIER)),
    ]
    assert auth_setup.client.get("/api/auth/google/login", params=params).status_code == 400


def test_atomic_consumption_compiles_as_delete_returning():
    class Capture:
        def scalar(self, statement):
            sql = str(statement.compile(dialect=postgresql.dialect()))
            assert "DELETE FROM sessions" in sql and "RETURNING sessions.user_id" in sql
            assert "expires_at >" in sql and "token_hash =" in sql
            return "user-id"

    assert AuthRepository(Capture()).consume_handoff("hash", datetime.now(UTC)) == "user-id"


def test_pkce_standard_vector():
    assert (
        desktop_auth.challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk")
        == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    )


def test_desktop_callback_database_failure_is_sanitized(auth_setup, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    def fail():
        raise SQLAlchemyError("private database error")

    monkeypatch.setattr(auth_setup.repository, "commit", fail)
    response = desktop_finish(auth_setup)
    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication is temporarily unavailable"}
    assert "location" not in response.headers
    assert auth_setup.client.cookies.get(auth.SESSION_COOKIE) is None


def test_exchange_database_failure_never_returns_a_token(auth_setup, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    code = handoff(auth_setup)

    def fail(*args):
        raise SQLAlchemyError("private database error")

    monkeypatch.setattr(auth_setup.repository, "consume_handoff", fail)
    response = exchange(auth_setup, code)
    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication is temporarily unavailable"}
    assert len(auth_setup.repository.sessions) == 1


def test_native_logout_failure_does_not_delete_session(auth_setup, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    token = exchange(auth_setup, handoff(auth_setup)).json()["session_token"]

    def fail(*args):
        raise SQLAlchemyError("private database error")

    monkeypatch.setattr(auth_setup.repository, "delete_session", fail)
    response = auth_setup.client.post(
        "/api/auth/desktop/logout", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication is temporarily unavailable"}
    assert auth.token_hash(token) in auth_setup.repository.sessions


def test_native_me_database_failure_is_sanitized(auth_setup, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    token = exchange(auth_setup, handoff(auth_setup)).json()["session_token"]

    def fail(*args):
        raise SQLAlchemyError("private database error")

    monkeypatch.setattr(auth_setup.repository, "user_for_session", fail)
    response = auth_setup.client.get(
        "/api/auth/desktop/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 503
    assert response.json() == {"detail": "Authentication is temporarily unavailable"}
