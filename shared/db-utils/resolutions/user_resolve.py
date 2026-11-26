"""Resolve users by Discord ID or name, creating users when necessary."""

from ..crud.user_select import (
    select_user_by_discord_id,
    select_users_by_name,
)
from ..crud.user_insert import insert_user, LOCK_USERS
from ..crud.query import query_rows


async def resolve_user(discord_id, name, *, connection):
    """Resolve a user and return their internal user_id.

    Resolution order:
        1. Match by Discord ID.
        2. Match by exact name and assign Discord ID.
        3. Create a new user.

    Requires an active database transaction.
    """

    if not isinstance(discord_id, str) or not discord_id.isdigit():
        raise ValueError("Invalid Discord ID.")

    # Prevent concurrent user resolution from creating duplicates.
    await connection.execute(LOCK_USERS)

    # 1. Match by Discord ID.
    existing = await select_user_by_discord_id(
        discord_id,
        connection=connection
    )

    if existing is not None:
        return existing["user_id"]

    # A valid name is required for the remaining resolution steps.
    if not isinstance(name, str) or not name.strip():
        raise ValueError("A valid name is required.")

    name = name.strip()

    # 2. Match by name.
    matches = await select_users_by_name(
        name,
        connection=connection
    )

    if len(matches) > 1:
        raise ValueError("Multiple users match this name.")

    if len(matches) == 1:
        existing = matches[0]

        if existing["discord_id"] not in (None, discord_id):
            raise ValueError(
                "User is associated with another Discord ID."
            )

        rows = await query_rows(
            """
            UPDATE public.users
            SET discord_id = $1
            WHERE user_id = $2
            RETURNING user_id
            """,
            [discord_id, existing["user_id"]],
            connection=connection
        )

        return rows[0]["user_id"]

    # 3. Create a new user.
    created = await insert_user(
        {
            "name": name,
            "discord_id": discord_id
        },
        connection=connection
    )

    return created["user_id"]
