from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings


Base = declarative_base()


settings = get_settings()
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    pool_recycle=300,
    # Disable psycopg3's prepared statement cache to avoid
    # DuplicatePreparedStatement errors on recycled connections.
    connect_args={"prepare_threshold": None},
)


# Auto-kill connections that sit idle in a transaction for more than 5 minutes.
# This prevents leaked sessions from holding row locks indefinitely.
# Uses a connect event (not connect_args options) because Supabase/PgBouncer
# strips libpq options.
@event.listens_for(engine, "connect")
def _set_pg_session_timeout(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("SET idle_in_transaction_session_timeout = '300s'")
    cursor.close()
    dbapi_conn.commit()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# Attach Postgres-level egress tracking hooks
try:
    from app.observability.pg_egress import install_pg_egress_hooks

    install_pg_egress_hooks(engine)
except Exception:
    pass  # graceful degradation if observability module fails


@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
