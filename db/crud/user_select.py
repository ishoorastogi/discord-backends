"""Look up users (Python version of the Node.js select file).

Pass username and password to run as a specific database role. Leave them out
to use the default account from .env.
"""
from crud.query import query_rows
from crud.user_queries import matching_users_query


async def select_users_by_name(name, username=None, password=None):
    """Members whose full name matches (case and extra spaces ignored). Returns a list."""
    sql, values = matching_users_query(name)
    return await query_rows(sql, values, username, password)


async def select_users_by_name_or_nickname(query, username=None, password=None):
    """Members whose name contains the text, or whose nickname matches it.
    If one member's full name matches exactly, only that member is returned. Returns a list."""
    sql, values = matching_users_query(query, "lookup")
    return await query_rows(sql, values, username, password)


async def select_user_by_id(user_id, username=None, password=None):
    """The member with this user_id, or None."""
    rows = await query_rows(
        "SELECT * FROM public.users WHERE user_id = $1", [user_id], username, password
    )
    return rows[0] if rows else None


async def select_user_by_discord_id(discord_id, username=None, password=None):
    """The member with this Discord ID (a string), or None."""
    rows = await query_rows(
        "SELECT * FROM public.users WHERE discord_id = $1", [discord_id], username, password
    )
    return rows[0] if rows else None