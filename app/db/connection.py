import logging
from urllib.parse import quote_plus
from uuid import UUID
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None


def get_connection_string() -> str:
    settings = get_settings()
    if settings.ENVIRONMENT == "development":
        return "postgresql://postgres:postgres@localhost:5432/realtor_ai"
    # Extract just the project ref (e.g. "ptgdqauzzlkbtqyaddim" from "https://ptgdqauzzlkbtqyaddim.supabase.co")
    host = settings.SUPABASE_URL.replace("https://", "").replace("http://", "")
    project_ref = host.split(".")[0]
    password = quote_plus(settings.SUPABASE_SERVICE_KEY)
    return f"postgresql://postgres.{project_ref}:{password}@aws-0-us-east-1.pooler.supabase.com:6543/postgres"


def init_pool(min_size: int = 2, max_size: int = 20) -> None:
    """Initialize the global connection pool. Call once at app startup."""
    global _pool
    if _pool is not None:
        return
    _pool = ConnectionPool(
        get_connection_string(),
        min_size=min_size,
        max_size=max_size,
        kwargs={"row_factory": dict_row},
    )
    logger.info(f"DB pool initialized (min={min_size}, max={max_size})")


def close_pool() -> None:
    """Close the global connection pool. Call at app shutdown."""
    global _pool
    if _pool:
        _pool.close()
        _pool = None
        logger.info("DB pool closed")


def get_db_connection() -> psycopg.Connection:
    """Get a connection from the pool (context-managed).

    Usage:
        with get_db_connection() as conn:
            ...
    If the pool hasn't been initialized (e.g. during tests), falls back
    to a direct connection for backward compatibility.
    """
    if _pool is not None:
        return _pool.connection()
    # Fallback for tests / scripts that haven't called init_pool()
    return psycopg.connect(get_connection_string(), row_factory=dict_row)


async def get_async_connection() -> psycopg.AsyncConnection:
    """Get an async database connection with dict row factory."""
    return await psycopg.AsyncConnection.connect(
        get_connection_string(), row_factory=dict_row
    )


def set_agent_context(conn: psycopg.Connection, agent_id: UUID) -> None:
    """Set the RLS context variable for agent isolation."""
    conn.execute("SELECT set_config('app.current_agent_id', %s, true)", [str(agent_id)])


async def async_set_agent_context(
    conn: psycopg.AsyncConnection, agent_id: UUID
) -> None:
    """Set the RLS context variable for agent isolation (async)."""
    await conn.execute(
        "SELECT set_config('app.current_agent_id', %s, true)", [str(agent_id)]
    )


def execute_query(
    query: str,
    params: list | tuple | None = None,
    agent_id: UUID | None = None,
    fetch_one: bool = False,
    fetch_all: bool = True,
) -> Any:
    """Execute a query with optional RLS context. Returns dict rows."""
    with get_db_connection() as conn:
        if agent_id:
            set_agent_context(conn, agent_id)
        with conn.cursor() as cur:
            cur.execute(query, params)
            if fetch_one:
                return cur.fetchone()
            if fetch_all:
                return cur.fetchall()
            conn.commit()
            return None


def execute_insert(
    query: str,
    params: list | tuple | None = None,
    agent_id: UUID | None = None,
) -> dict | None:
    """Execute an insert and return the inserted row."""
    with get_db_connection() as conn:
        if agent_id:
            set_agent_context(conn, agent_id)
        with conn.cursor() as cur:
            cur.execute(query, params)
            conn.commit()
            result = cur.fetchone()
            return result


def execute_update(
    query: str,
    params: list | tuple | None = None,
    agent_id: UUID | None = None,
) -> dict | None:
    """Execute an update and return the updated row."""
    return execute_insert(query, params, agent_id)
