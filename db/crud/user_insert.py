"""Insert, bulk insert, and upsert for users (Python version of the Node.js insert file)."""
from crud.query import query_rows, with_transaction
from crud.user_queries import (
    insert_query,
    matching_users_query,
    unique_user,
    user_fields,
)

LOCK_USERS = "LOCK TABLE public.users IN SHARE ROW EXCLUSIVE MODE"


async def insert_user(user, username=None, password=None):
    """Add one user and return the new row."""
    sql, values = insert_query(user_fields(user))
    rows = await query_rows(sql, values, username, password)
    return rows[0]


async def insert_users(users, username=None, password=None):
    """Add many users in one transaction: all are saved, or none are."""
    if not isinstance(users, list):
        raise TypeError("Provide a list of users.")
    queries = [insert_query(user_fields(user)) for user in users]

    async def work(conn):
        rows = []
        for sql, values in queries:
            rows.append(dict(await conn.fetchrow(sql, *values)))
        return rows

    return await with_transaction(work, username, password)


async def upsert_user(user, username=None, password=None):
    """Insert the user, or update the existing one with the same name.

    Names have no unique constraint, so the table is locked while this runs.
    That stops two calls from both inserting the same missing name."""
    fields = user_fields(user)
    name = user.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Upsert requires a name to identify an existing user.")

    async def work(conn):
        await conn.execute(LOCK_USERS)
        sql, values = matching_users_query(name)
        matches = [dict(r) for r in await conn.fetch(sql, *values)]
        existing = unique_user(matches)  # raises if more than one match
        if existing is None:
            sql, values = insert_query(fields)
            return dict(await conn.fetchrow(sql, *values))
        updates = [(column, value) for column, value in fields if column != "name"]
        if not updates:
            return existing
        assignments = ", ".join(f'"{column}" = ${i + 1}' for i, (column, _) in enumerate(updates))
        values = [value for _, value in updates] + [existing["user_id"]]
        row = await conn.fetchrow(
            f"UPDATE public.users SET {assignments} "
            f"WHERE user_id = ${len(values)} RETURNING *",
            *values,
        )
        return dict(row)

    return await with_transaction(work, username, password)