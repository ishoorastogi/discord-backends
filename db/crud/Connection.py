"""Database connection pools. Settings come from the .env file (never commit it).

There is one default pool (from .env) and one cached pool per database role, so
callers can connect as a specific actor by passing a username and password,
the same way the Node.js code does from the frontend ishan wrote
"""
import os

import asyncpg
from dotenv import load_dotenv
from pgvector.asyncpg import register_vector

load_dotenv()

_pool = None
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
    """Create the default pool once, when the app starts."""
    global _pool
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
    global _pool
    for pool in _role_pools.values():
        await pool.close()
    _role_pools.clear()
    if _pool is not None:
        await _pool.close()
        _pool = None