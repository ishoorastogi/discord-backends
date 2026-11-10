"""Update a user by name (Python version of the Node.js update file).

Behaves like an update-or-create: if no member matches, a new one is created.
"""
from crud.query import with_transaction
from crud.user_queries import (
    insert_query,
    matching_users_query,
    normalize_name,
    unique_user,
    user_fields,
)

LOCK_USERS = "LOCK TABLE public.users IN SHARE ROW EXCLUSIVE MODE"


async def update_user_by_name(name, updates, username=None, password=None):
    """Exact full names take priority; otherwise a unique name prefix may identify a user.

    Returns a dict: created (bool), user (dict), updated_columns (list), errors (list)."""
    match_sql, match_values = matching_users_query(name, "prefix")
    fields = user_fields(updates)
    rename = next((f for f in fields if f[0] == "name"), None)
    if rename and (not isinstance(rename[1], str) or not rename[1].strip()):
        raise ValueError("Name is required.")

    async def work(conn):
        use = list(fields)
        await conn.execute(LOCK_USERS)
        rows = [dict(r) for r in await conn.fetch(match_sql, *match_values)]
        existing = unique_user(rows)  # raises if the name matches several members
        errors = []

        if rename:
            sql, values = matching_users_query(rename[1])
            conflicts = [dict(r) for r in await conn.fetch(sql, *values)]
            existing_id = existing["user_id"] if existing else None
            if any(row["user_id"] != existing_id for row in conflicts):
                errors.append({
                    "category": "name",
                    "value": rename[1],
                    "code": "AMBIGUOUS_USER",
                    "message": "Another member already has that name. The name was not changed.",
                })
                use = [f for f in use if f is not rename]

        if not use:
            return {
                "created": False,
                "user": existing or {"name": name},
                "updated_columns": [],
                "errors": errors,
            }

        if existing:
            assignments = ", ".join(f'"{column}" = ${i + 1}' for i, (column, _) in enumerate(use))
            values = [value for _, value in use] + [existing["user_id"]]
            row = await conn.fetchrow(
                f"UPDATE public.users SET {assignments} "
                f"WHERE user_id = ${len(values)} RETURNING *",
                *values,
            )
        else:
            new_fields = user_fields({"name": normalize_name(name), **dict(use)})
            sql, values = insert_query(new_fields)
            row = await conn.fetchrow(sql, *values)

        return {
            "created": existing is None,
            "user": dict(row),
            "updated_columns": [column for column, _ in use],
            "errors": errors,
        }

    return await with_transaction(work, username, password)