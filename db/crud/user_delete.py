"""Delete a user by name (Python version of the Node.js delete file)."""
from crud.query import with_transaction
from crud.user_queries import (
    MemberChangedError,
    matching_users_query,
    unique_user,
)

LOCK_USERS = "LOCK TABLE public.users IN SHARE ROW EXCLUSIVE MODE"


async def delete_user_by_name(name, expected_user=None, username=None, password=None):
    """Delete the member with this exact name and return the deleted row.

    Returns None if nobody matches. If expected_user is given and the member's
    record no longer equals it, nothing is deleted and MemberChangedError is raised.
    That protects against deleting a record that changed after the user confirmed it."""
    sql, values = matching_users_query(name)

    async def work(conn):
        await conn.execute(LOCK_USERS)
        rows = [dict(r) for r in await conn.fetch(sql, *values)]
        existing = unique_user(rows)  # raises if more than one match
        if existing is None:
            return None
        if expected_user is not None and existing != expected_user:
            raise MemberChangedError(
                "That member's record changed after confirmation. "
                "Request deletion again. No records were deleted."
            )
        await conn.execute(
            "DELETE FROM public.users WHERE user_id = $1", existing["user_id"]
        )
        return existing

    return await with_transaction(work, username, password)