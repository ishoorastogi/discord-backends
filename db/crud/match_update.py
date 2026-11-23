"""Update the score of an existing match.

Only similarity_score can change. The pair (user_id, internship_id) identifies the
match, so to move a match to another pair, delete it and create a new one.
"""
from db.crud.internship_queries import check_internship_id
from db.crud.match_queries import (
    check_match_id,
    match_fields,
    update_assignments,
)
from db.crud.query import query_rows
from db.crud.resume_queries import check_user_id


async def update_match(match_id, updates, username=None, password=None):
    """Change a match's score by its match_id and return the updated row.

    `updates` is {"similarity_score": 0.93}. Returns None if there is no such match
    (use upsert_match to create one)."""
    match_id = check_match_id(match_id)
    fields = match_fields(updates, for_insert=False)
    values = [value for _, value in fields] + [match_id]
    rows = await query_rows(
        f"UPDATE public.matches SET {update_assignments(fields)} "
        f"WHERE match_id = ${len(values)} RETURNING *",
        values, username, password,
    )
    return rows[0] if rows else None


async def update_match_by_pair(user_id, internship_id, updates, username=None, password=None):
    """Same as update_match, but finds the match by user_id and internship_id, which
    is what the Match Engine knows. Returns the updated row, or None."""
    user_id = check_user_id(user_id)
    internship_id = check_internship_id(internship_id)
    fields = match_fields(updates, for_insert=False)
    values = [value for _, value in fields] + [user_id, internship_id]
    rows = await query_rows(
        f"UPDATE public.matches SET {update_assignments(fields)} "
        f"WHERE user_id = ${len(values) - 1} AND internship_id = ${len(values)} RETURNING *",
        values, username, password,
    )
    return rows[0] if rows else None