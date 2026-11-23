"""Delete matches. The user and the internship are not affected."""
from db.crud.internship_queries import check_internship_id
from db.crud.match_queries import check_match_id
from db.crud.query import query_rows
from db.crud.resume_queries import check_user_id


async def delete_match(match_id, username=None, password=None):
    """Delete the match with this match_id and return the deleted row, or None."""
    rows = await query_rows(
        "DELETE FROM public.matches WHERE match_id = $1 RETURNING *",
        [check_match_id(match_id)], username, password,
    )
    return rows[0] if rows else None


async def delete_match_by_pair(user_id, internship_id, username=None, password=None):
    """Delete the match between this user and this internship. Returns the deleted
    row, or None if they weren't matched."""
    rows = await query_rows(
        "DELETE FROM public.matches WHERE user_id = $1 AND internship_id = $2 RETURNING *",
        [check_user_id(user_id), check_internship_id(internship_id)], username, password,
    )
    return rows[0] if rows else None