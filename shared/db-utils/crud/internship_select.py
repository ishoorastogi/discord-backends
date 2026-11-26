"""Look up internships.

An internship comes back as a dict with every column: id, company, title,
description, location, role_type, requirements, url, and embedding. The embedding is
a numpy array of 384 floats (use .tolist() for a plain list), or None if never set.
"""
from .internship_queries import check_internship_id, check_url, select_query
from .query import query_rows


async def select_internship_by_id(internship_id, username=None, password=None):
    """The internship with this id, or None."""
    rows = await query_rows(
        "SELECT * FROM public.internships WHERE id = $1",
        [check_internship_id(internship_id)], username, password,
    )
    return rows[0] if rows else None


async def select_internship_by_url(url, username=None, password=None):
    """The internship with this url, or None. This is the 'is it new?' check: None
    means the listing hasn't been stored yet."""
    rows = await query_rows(
        "SELECT * FROM public.internships WHERE url = $1",
        [check_url(url)], username, password,
    )
    return rows[0] if rows else None


async def select_internships(filters=None, limit=100, username=None, password=None):
    """A list of internships, oldest id first.

    filters is an optional dict using company, title, location, and role_type, for
    example {"role_type": "intern", "location": "Dallas"}. Every filter must match the
    whole value, ignoring case. limit is 1 to 1000 (default 100). Returns [] if nothing
    matches."""
    sql, values = select_query(filters, limit)
    return await query_rows(sql, values, username, password)