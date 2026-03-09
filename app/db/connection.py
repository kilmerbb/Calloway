import json
from uuid import UUID
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.config import get_settings


def get_connection_string() -> str:
    settings = get_settings()
    # Supabase connection string derived from project URL
    # Format: postgresql://postgres:[SERVICE_KEY]@[HOST]:5432/postgres
    # For local dev, use DATABASE_URL env var or default to local postgres
    if settings.ENVIRONMENT == "development":
        return "postgresql://postgres:postgres@localhost:5432/realtor_ai"
    # Extract host from Supabase URL
    host = settings.SUPABASE_URL.replace("https://", "").replace("http://", "")
    return f"postgresql://postgres.{host}:{settings.SUPABASE_SERVICE_KEY}@aws-0-us-east-1.pooler.supabase.com:6543/postgres"


def get_db_connection() -> psycopg.Connection:
    """Get a new database connection with dict row factory."""
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
