import uuid
from datetime import datetime

from sqlalchemy import DateTime, MetaData, create_engine, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import settings

# SQLAlchemy 2.0 + psycopg3 engine (never a raw driver connection in handlers); schema via alembic.
# The platform injects a bare `postgresql://` DSN, which SQLAlchemy maps to psycopg2 — but this project
# ships psycopg3. Pin the psycopg3 driver so create_engine imports cleanly.
_url = settings.database_url
if _url.startswith("postgresql://"):
    _url = "postgresql+psycopg://" + _url[len("postgresql://") :]
# pool_pre_ping recycles a dead connection on checkout; statement_timeout stops any query hanging forever.
engine = create_engine(_url, pool_pre_ping=True, connect_args={"options": "-c statement_timeout=30000"})
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

# Deterministic constraint/index names → clean `alembic revision --autogenerate` diffs.
_NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=_NAMING)


class PKMixin:
    # UUIDv7 primary key, generated SERVER-SIDE by PostgreSQL 18's uuidv7(): time-ordered, so it keeps
    # B-tree index locality like a serial while staying unguessable. Never a random v4, never a bare serial.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=func.uuidv7())


class TimestampMixin:
    # timestamptz ALWAYS (never a naive datetime); set + maintained by the DB.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
