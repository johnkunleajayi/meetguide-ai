from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.oauth import create_oauth, state_signing_key
from app.db.session import create_database_engine, create_session_factory


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings if settings is not None else get_settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = create_database_engine(configuration)
        application.state.engine = engine
        application.state.session_factory = create_session_factory(engine)
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(title=configuration.app_name, lifespan=lifespan)
    application.state.settings = configuration
    application.state.oauth = create_oauth(configuration)
    application.add_middleware(
        SessionMiddleware,
        secret_key=state_signing_key(configuration),
        session_cookie="meetguide_oauth_state",
        max_age=600,
        path="/api/auth/google",
        same_site="lax",
        https_only=configuration.secure_cookies,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configuration.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-Document-Name"],
    )
    application.include_router(api_router)
    return application
