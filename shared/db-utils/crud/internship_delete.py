"""Delete internships. Matches for a deleted internship are removed too
(ON DELETE CASCADE in the schema)."""
from .internship_queries import check_internship_id, check_url
from .query import query_rows


async def delete_internship(internship_id, username=None, password=None):
    """Delete the internship with this id and return the deleted row, or None if
    there was none."""
    rows = await query_rows(
        "DELETE FROM public.internships WHERE id = $1 RETURNING *",
        [check_internship_id(internship_id)], username, password,
    )
    return rows[0] if rows else None


async def delete_internship_by_url(url, username=None, password=None):
    """Delete the internship with this url and return the deleted row, or None."""
    rows = await query_rows(
        "DELETE FROM public.internships WHERE url = $1 RETURNING *",
        [check_url(url)], username, password,
    )
    return rows[0] if rows else None