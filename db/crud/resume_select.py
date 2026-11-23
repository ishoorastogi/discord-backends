"""Look up resumes.

A resume comes back as a dict: user_id plus resume_text, skills, experience, and
education. Each vector is a numpy array of 384 floats (use .tolist() for a plain
list). A column that was never set is None.
"""
from db.crud.query import query_rows
from db.crud.resume_queries import check_user_id


async def select_resume_by_user_id(user_id, username=None, password=None):
    """The resume for this user_id, or None."""
    rows = await query_rows(
        "SELECT * FROM public.resumes WHERE user_id = $1",
        [check_user_id(user_id)], username, password,
    )
    return rows[0] if rows else None


async def select_resume_by_discord_id(discord_id, username=None, password=None):
    """The resume for the member with this Discord ID (a string), or None.
    Saves looking up the user_id first."""
    if not isinstance(discord_id, str):
        raise TypeError("Discord IDs must be strings to preserve their digits.")
    rows = await query_rows(
        "SELECT r.* FROM public.resumes r "
        "JOIN public.users u ON u.user_id = r.user_id "
        "WHERE u.discord_id = $1",
        [discord_id], username, password,
    )
    return rows[0] if rows else None