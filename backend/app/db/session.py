from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


def create_database_engine(settings: Settings) -> Engine:
    # Creating an engine is lazy: neither startup nor health opens a connection.
    return create_engine(settings.database_url.get_secret_value(), pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


def get_db(request: Request) -> Iterator[Session]:
    """Future routes opt in to a request-scoped session and own their transaction."""
    with request.app.state.session_factory() as session:
        yield session
