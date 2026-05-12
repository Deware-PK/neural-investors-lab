from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, MetaData, String, Table, create_engine, insert, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import Settings, get_settings


metadata = MetaData()

analysis_outputs = Table(
    "analysis_outputs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("ticker", String(16), nullable=False, index=True),
    Column("output", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def create_postgres_engine(settings: Settings | None = None) -> Engine:
    resolved_settings = settings or get_settings()
    return create_engine(resolved_settings.postgres_url, pool_pre_ping=True)


def create_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    resolved_engine = engine or create_postgres_engine()
    return sessionmaker(bind=resolved_engine, autoflush=False, autocommit=False)


def get_postgres_session(session_factory: sessionmaker[Session] | None = None) -> Generator[Session, None, None]:
    resolved_factory = session_factory or create_session_factory()
    session = resolved_factory()
    try:
        yield session
    finally:
        session.close()


def initialize_database(engine: Engine | None = None) -> None:
    resolved_engine = engine or create_postgres_engine()
    metadata.create_all(resolved_engine)


def persist_analysis_output(
    session: Session,
    ticker: str,
    output: dict[str, Any],
    record_id: UUID | None = None,
    created_at_override: datetime | None = None,
) -> str:
    resolved_record_id = record_id or uuid4()
    resolved_created_at = created_at_override or datetime.now(UTC)
    session.execute(
        insert(analysis_outputs).values(
            id=str(resolved_record_id),
            ticker=ticker.upper(),
            output=output,
            created_at=resolved_created_at,
        )
    )
    session.commit()
    return str(resolved_record_id)


def fetch_historical_analysis_outputs(session: Session, actions: list[str] | None = None) -> list[dict[str, Any]]:
    statement = select(
        analysis_outputs.c.id,
        analysis_outputs.c.ticker,
        analysis_outputs.c.output,
        analysis_outputs.c.created_at,
    ).order_by(analysis_outputs.c.created_at.asc())
    rows = session.execute(statement).mappings().all()
    if actions is None:
        return [dict(row) for row in rows]
    normalized_actions = {action.lower() for action in actions}
    return [
        dict(row)
        for row in rows
        if str(row["output"].get("action", "")).lower() in normalized_actions
    ]
