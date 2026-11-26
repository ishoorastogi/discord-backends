"""Delete resumes. The member stays; only their resume is removed."""
from .query import query_rows
from .resume_queries import check_user_id


async def delete_resume(user_id, username=None, password=None):
    """Delete this user's resume and return the deleted row, or None if they had none."""
    rows = await query_rows(
        "DELETE FROM public.resumes WHERE user_id = $1 RETURNING *",
        [check_user_id(user_id)], username, password,
    )
    return rows[0] if rows else None


async def delete_resume_by_discord_id(discord_id, username=None, password=None):
    """Delete the resume of the member with this Discord ID (a string).
    Returns the deleted row, or None if there was nothing to delete."""
    if not isinstance(discord_id, str):
        raise TypeError("Discord IDs must be strings to preserve their digits.")
    rows = await query_rows(
        "DELETE FROM public.resumes WHERE user_id = "
        "(SELECT user_id FROM public.users WHERE discord_id = $1) RETURNING *",
        [discord_id], username, password,
    )
    return rows[0] if rows else None