"""Database connection pools. Settings come from the .env file (never commit it).

There is one default pool (from .env) and one cached pool per database role, so
callers can connect as a specific actor by passing a username and password,
the same way the Node.js code does from the frontend ishan wrote
"""
import asyncio
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv
from pgvector.asyncpg import register_vector

load_dotenv(Path(__file__).resolve().parents[3] / "db" / ".env")

_pool = None
_pool_init_lock = None
_role_pools = {}


async def _init_connection(conn):
    """Let asyncpg send/receive pgvector columns, if pgvector exists in this database."""
    try:
        await register_vector(conn)
    except ValueError:
        pass  # pgvector isn't installed here; fine for tables without vectors


def _settings(user, password):
    return dict(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        user=user,
        password=password,
        database=os.getenv("POSTGRES_DB"),
        init=_init_connection,
    )


async def init_pool(min_size=2, max_size=10):
    """Create the default pool on first use, sharing it across callers."""
    global _pool, _pool_init_lock
    if _pool is None:
        if _pool_init_lock is None:
            _pool_init_lock = asyncio.Lock()
        async with _pool_init_lock:
            if _pool is None:
                _pool = await asyncpg.create_pool(
                    min_size=min_size,
                    max_size=max_size,
                    **_settings(os.getenv("POSTGRES_USER"), os.getenv("POSTGRES_PASSWORD")),
                )
    return _pool


def get_pool():
    if _pool is None:
        raise RuntimeError("Call await init_pool() before using the database.")
    return _pool


async def get_role_pool(username, password):
    """Pool that connects as a specific database role (cached per username)."""
    pool = _role_pools.get(username)
    if pool is None:
        pool = await asyncpg.create_pool(
            min_size=1, max_size=5, **_settings(username, password)
        )
        _role_pools[username] = pool
    return pool


async def close_pool():
    """Close every pool when the app shuts down."""
    global _pool, _pool_init_lock
    pools = list(_role_pools.values())
    if _pool is not None:
        pools.append(_pool)
    _role_pools.clear()
    _pool = None
    _pool_init_lock = None

    results = await asyncio.gather(*(pool.close() for pool in pools), return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            raise result
