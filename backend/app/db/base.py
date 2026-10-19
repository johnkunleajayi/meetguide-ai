from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared metadata for future models; no domain tables exist yet."""
