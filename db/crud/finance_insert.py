"""Insert finance records, one at a time or a whole batch.

A finance record is a dict with type ('income', 'expense', or 'dues') and amount
(both required), and an optional user_id. If a user_id is given, that member must exist.

There is no upsert for finances. A finance record has no natural unique key, so an
"update if it exists" call could silently overwrite or double-count a payment. Each
payment is its own row: use insert for a new one and update_finance to correct one.

Pass the finance_user role's username and password, or leave them out to use the
default account from .env.
"""
from db.crud.finance_queries import finance_fields, insert_query
from db.crud.query import query_rows, with_transaction


async def insert_finance(finance, username=None, password=None):
    """Add one finance record and return the new row (including its generated finance_id).

    Raises asyncpg.ForeignKeyViolationError if user_id doesn't exist."""
    sql, values = insert_query(finance_fields(finance))
    rows = await query_rows(sql, values, username, password)
    return rows[0]


async def insert_finances(finances, username=None, password=None):
    """Add many finance records in one transaction: all are saved, or none are.
    For example, recording dues for every member at once. Returns the list of new rows."""
    if not isinstance(finances, list):
        raise TypeError("Provide a list of finance records.")
    queries = [insert_query(finance_fields(item)) for item in finances]

    async def work(conn):
        rows = []
        for sql, values in queries:
            rows.append(dict(await conn.fetchrow(sql, *values)))
        return rows

    return await with_transaction(work, username, password)