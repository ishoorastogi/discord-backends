"""Python version of the Node.js ../query module: query_rows and with_transaction.

Pass username and password to run as a specific database role. Leave them out
to use the default account from .env.
"""
from .Connection import get_role_pool, init_pool

def _plain(value):
    """Newer pgvector versions hand back Vector objects. Turn them into numpy arrays
    so callers always get the same type, whatever pgvector version is installed."""
    return value.to_numpy() if hasattr(value, "to_numpy") else value

async def _pool_for(username, password):
    if username:
        return await get_role_pool(username, password)
    return await init_pool()


async def query_rows(
    sql,
    values=(),
    username=None,
    password=None,
    *,
    connection=None
):
    """Run a query using an existing connection or a pooled connection."""

    async def execute(conn):
        rows = await conn.fetch(sql, *values)

        return [
            {
                key: _plain(value)
                for key, value in row.items()
            }
            for row in rows
        ]

    if connection is not None:
        return await execute(connection)

    pool = await _pool_for(username, password)

    async with pool.acquire() as conn:
        return await execute(conn)


async def with_transaction(fn, username=None, password=None):
    """Run `await fn(conn)` inside a transaction.
    Commits if fn returns, rolls back if fn raises."""
    pool = await _pool_for(username, password)
    async with pool.acquire() as conn:
        async with conn.transaction():
            return await fn(conn)
