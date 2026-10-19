import secrets

from authlib.integrations.starlette_client import OAuth

from app.core.config import Settings


def create_oauth(settings: Settings) -> OAuth:
    oauth = OAuth()
    oauth.register(
        "google",
        client_id=settings.google_client_id,
        client_secret=(
            settings.google_client_secret.get_secret_value()
            if settings.google_client_secret
            else None
        ),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile", "code_challenge_method": "S256"},
    )
    return oauth


def state_signing_key(settings: Settings) -> str:
    if settings.auth_state_secret is not None:
        return settings.auth_state_secret.get_secret_value()
    # Local development only; restarts invalidate in-flight OAuth handshakes, not DB sessions.
    return secrets.token_urlsafe(32)
