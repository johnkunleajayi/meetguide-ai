from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.api.auth import NO_STORE
from app.context.api import current_user
from app.cues.api import cue_user
from app.db.auth_repository import get_auth_repository
from app.preparations.domain import PreparationInput
from app.preparations.repository import get_preparations
from app.preparations.snapshot import freeze

router = APIRouter(prefix="/preparations", tags=["session preparation"])


def preparation_user(request: Request, repository=Depends(get_auth_repository)):
    return (
        cue_user(request, repository)
        if request.headers.get("authorization")
        else current_user(request, repository)
    )


def execute(action):
    try:
        return action()
    except LookupError:
        raise HTTPException(
            404, "Preparation or selected document not found", headers=NO_STORE
        ) from None
    except ValueError as error:
        raise HTTPException(422, str(error), headers=NO_STORE) from None
    except SQLAlchemyError:
        raise HTTPException(
            503, "Preparation is unavailable. Check migrations and retry.", headers=NO_STORE
        ) from None


@router.get("")
def list_preparations(
    response: Response, user=Depends(preparation_user), repository=Depends(get_preparations)
):
    response.headers.update(NO_STORE)
    return execute(lambda: repository.list(user.id))


@router.post("", status_code=201)
def create(
    payload: PreparationInput,
    response: Response,
    user=Depends(preparation_user),
    repository=Depends(get_preparations),
):
    response.headers.update(NO_STORE)
    return execute(lambda: repository.save(user.id, payload))


@router.put("/{preparation_id}")
def update(
    preparation_id: UUID,
    payload: PreparationInput,
    response: Response,
    user=Depends(preparation_user),
    repository=Depends(get_preparations),
):
    response.headers.update(NO_STORE)
    return execute(lambda: repository.save(user.id, payload, preparation_id))


@router.post("/{preparation_id}/activate", status_code=204)
def activate(
    preparation_id: UUID, user=Depends(preparation_user), repository=Depends(get_preparations)
):
    execute(lambda: repository.activate(user.id, preparation_id))
    return Response(status_code=204, headers=NO_STORE)


class FreezeInput(BaseModel):
    expected_updated_at: datetime


@router.post("/{preparation_id}/freeze")
def start(
    payload: FreezeInput,
    preparation_id: UUID,
    request: Request,
    response: Response,
    user=Depends(cue_user),
    repository=Depends(get_preparations),
):
    view = execute(lambda: repository.view(user.id, preparation_id))
    if view.updated_at != payload.expected_updated_at:
        raise HTTPException(409, "Preparation changed. Refresh before starting.", headers=NO_STORE)
    response.headers.update(NO_STORE)
    return {"preparation_token": freeze(request.app, user.id, view), "preparation": view}
