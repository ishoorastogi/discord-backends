"""Python version of the Node.js ../query module: query_rows and with_transaction.

Pass username and password to run as a specific database role. Leave them out
to use the default account from .env.
"""
from crud.Connection import get_pool, get_role_pool


async def _pool_for(username, password):
    if username:
        return await get_role_pool(username, password)
    return get_pool()


async def query_rows(sql, values=(), username=None, password=None):
    """Run one query and return the rows as a list of dicts."""
    pool = await _pool_for(username, password)
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, *values)
        return [dict(row) for row in rows]


async def with_transaction(fn, username=None, password=None):
    """Run `await fn(conn)` inside a transaction.
    Commits if fn returns, rolls back if fn raises."""
    pool = await _pool_for(username, password)
    async with pool.acquire() as conn:
        async with conn.transaction():
            return await fn(conn)