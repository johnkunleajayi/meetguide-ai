"""Authenticated, immutable live scope. Signed metadata only; no live DB records."""

from itsdangerous import BadData, URLSafeTimedSerializer
from pydantic import ValidationError

from app.preparations.domain import PreparedContext

MAX_AGE = 12 * 60 * 60


def signer(application):
    return URLSafeTimedSerializer(
        application.state.preparation_signing_key, salt="meetguide-preparation-v1"
    )


def freeze(application, user_id, view):
    snapshot = PreparedContext(
        preparation_id=view.id,
        user_id=user_id,
        purpose=view.purpose,
        objective=view.objective,
        documents=view.documents,
    )
    return signer(application).dumps(snapshot.model_dump(mode="json"))


def resolve(application, user_id, token):
    if not token or len(token) > 12000:
        raise ValueError("Choose a preparation before starting the session")
    try:
        snapshot = PreparedContext.model_validate(signer(application).loads(token, max_age=MAX_AGE))
        if snapshot.user_id != user_id:
            raise ValueError
        return snapshot
    except BadData, ValidationError, ValueError, TypeError:
        raise ValueError(
            "Prepared session expired or is invalid. Stop and start a new session."
        ) from None
