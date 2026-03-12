import logging
from urllib.parse import quote_plus
from uuid import UUID
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, AsyncConnectionPool

from app.config import get_settings

logger = logging.getLogger(__name__)

_pool: ConnectionPool | None = None
_async_pool: AsyncConnectionPool | None = None


def get_connection_string() -> str:
    settings = get_settings()
    if settings.DATABASE_URL:
        return settings.DATABASE_URL
    if settings.ENVIRONMENT == "development":
        return "postgresql://postgres:postgres@localhost:5432/realtor_ai"
    # Fallback: build from Supabase env vars
    host = settings.SUPABASE_URL.replace("https://", "").replace("http://", "")
    project_ref = host.split(".")[0]
    password = quote_plus(settings.SUPABASE_SERVICE_KEY)
    return f"postgresql://postgres.{project_ref}:{password}@aws-0-us-east-1.pooler.supabase.com:6543/postgres"


# ============================================================
# Synchronous pool (kept for workers + backward compatibility)
# ============================================================

def init_pool(min_size: int = 2, max_size: int = 20) -> None:
    """Initialize the global synchronous connection pool. Call once at app startup."""
    global _pool
    if _pool is not None:
        return
    conninfo = get_connection_string()
    logger.info("Connecting to sync DB pool...")
    _pool = ConnectionPool(
        conninfo,
        min_size=min_size,
        max_size=max_size,
        kwargs={"row_factory": dict_row},
        open=False,  # Don't block startup waiting for connections
        timeout=10,
    )
    _pool.open(wait=False)  # Start filling pool in background
    logger.info(f"Sync DB pool initialized (min={min_size}, max={max_size})")


def close_pool() -> None:
    """Close the global synchronous connection pool. Call at app shutdown."""
    global _pool
    if _pool:
        _pool.close()
        _pool = None
        logger.info("Sync DB pool closed")


def get_db_connection() -> psycopg.Connection:
    """Get a synchronous connection from the pool (context-managed).

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


# ============================================================
# Async pool (primary path for FastAPI handlers)
# ============================================================

async def init_async_pool(min_size: int = 2, max_size: int = 20) -> None:
    """Initialize the global async connection pool. Call once at app startup."""
    global _async_pool
    if _async_pool is not None:
        return
    conninfo = get_connection_string()
    logger.info("Connecting to async DB pool...")
    _async_pool = AsyncConnectionPool(
        conninfo,
        min_size=min_size,
        max_size=max_size,
        kwargs={"row_factory": dict_row},
        open=False,
        timeout=10,
    )
    await _async_pool.open(wait=False)
    logger.info(f"Async DB pool initialized (min={min_size}, max={max_size})")


async def close_async_pool() -> None:
    """Close the global async connection pool. Call at app shutdown."""
    global _async_pool
    if _async_pool:
        await _async_pool.close()
        _async_pool = None
        logger.info("Async DB pool closed")


async def get_async_db_connection() -> psycopg.AsyncConnection:
    """Get an async connection from the pool (async context-managed).

    Usage:
        async with get_async_db_connection() as conn:
            ...
    If the async pool hasn't been initialized, falls back to a direct connection.
    """
    if _async_pool is not None:
        return _async_pool.connection()
    # Fallback for tests / scripts
    return await psycopg.AsyncConnection.connect(
        get_connection_string(), row_factory=dict_row
    )


# Legacy alias — kept for any existing callers
async def get_async_connection() -> psycopg.AsyncConnection:
    """Get an async database connection with dict row factory.
    Deprecated: prefer get_async_db_connection() which uses the pool.
    """
    return await psycopg.AsyncConnection.connect(
        get_connection_string(), row_factory=dict_row
    )


# ============================================================
# RLS context helpers
# ============================================================

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


# ============================================================
# Synchronous query helpers (kept for workers + backward compat)
# ============================================================

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


# ============================================================
# Async query helpers (primary path for FastAPI handlers)
# ============================================================

async def async_execute_query(
    query: str,
    params: list | tuple | None = None,
    agent_id: UUID | None = None,
    fetch_one: bool = False,
    fetch_all: bool = True,
) -> Any:
    """Execute a query asynchronously with optional RLS context. Returns dict rows."""
    async with get_async_db_connection() as conn:
        if agent_id:
            await async_set_agent_context(conn, agent_id)
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            if fetch_one:
                return await cur.fetchone()
            if fetch_all:
                return await cur.fetchall()
            await conn.commit()
            return None


async def async_execute_insert(
    query: str,
    params: list | tuple | None = None,
    agent_id: UUID | None = None,
) -> dict | None:
    """Execute an insert asynchronously and return the inserted row."""
    async with get_async_db_connection() as conn:
        if agent_id:
            await async_set_agent_context(conn, agent_id)
        async with conn.cursor() as cur:
            await cur.execute(query, params)
            await conn.commit()
            result = await cur.fetchone()
            return result


async def async_execute_update(
    query: str,
    params: list | tuple | None = None,
    agent_id: UUID | None = None,
) -> dict | None:
    """Execute an update asynchronously and return the updated row."""
    return await async_execute_insert(query, params, agent_id)
