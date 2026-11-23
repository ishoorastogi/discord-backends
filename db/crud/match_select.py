"""Look up matches.

A match comes back as a dict: match_id, user_id, internship_id, and similarity_score
(a float, or None). Lists come back as a list of those dicts, [] if nothing matches.
"""
from db.crud.internship_queries import check_internship_id
from db.crud.match_queries import check_limit, check_match_id
from db.crud.query import query_rows
from db.crud.resume_queries import check_user_id


async def select_match_by_id(match_id, username=None, password=None):
    """The match with this match_id, or None."""
    rows = await query_rows(
        "SELECT * FROM public.matches WHERE match_id = $1",
        [check_match_id(match_id)], username, password,
    )
    return rows[0] if rows else None


async def select_match_by_pair(user_id, internship_id, username=None, password=None):
    """The match between this user and this internship, or None."""
    rows = await query_rows(
        "SELECT * FROM public.matches WHERE user_id = $1 AND internship_id = $2",
        [check_user_id(user_id), check_internship_id(internship_id)], username, password,
    )
    return rows[0] if rows else None


async def match_exists(user_id, internship_id, username=None, password=None):
    """True if this user was already matched to this internship, else False.
    This is the Match Engine's 'check match history' step."""
    rows = await query_rows(
        "SELECT EXISTS (SELECT 1 FROM public.matches "
        "WHERE user_id = $1 AND internship_id = $2) AS found",
        [check_user_id(user_id), check_internship_id(internship_id)], username, password,
    )
    return rows[0]["found"]


async def select_matches_for_user(user_id, limit=100, username=None, password=None):
    """A user's matches, best score first (matches with no score come last)."""
    return await query_rows(
        "SELECT * FROM public.matches WHERE user_id = $1 "
        "ORDER BY similarity_score DESC NULLS LAST, match_id LIMIT $2",
        [check_user_id(user_id), check_limit(limit)], username, password,
    )


async def select_matches_for_internship(internship_id, limit=100, username=None, password=None):
    """The matches for one internship, best score first (no score last)."""
    return await query_rows(
        "SELECT * FROM public.matches WHERE internship_id = $1 "
        "ORDER BY similarity_score DESC NULLS LAST, match_id LIMIT $2",
        [check_internship_id(internship_id), check_limit(limit)], username, password,
    )


async def select_match_details(match_id, username=None, password=None):
    """Everything the Discord message needs, in one dict, or None if there's no such match:
    match_id, similarity_score, user_id, discord_id, name, internship_id, company, title, url."""
    rows = await query_rows(
        "SELECT m.match_id, m.similarity_score, m.user_id, u.discord_id, u.name, "
        "m.internship_id, i.company, i.title, i.url "
        "FROM public.matches m "
        "JOIN public.users u ON u.user_id = m.user_id "
        "JOIN public.internships i ON i.id = m.internship_id "
        "WHERE m.match_id = $1",
        [check_match_id(match_id)], username, password,
    )
    return rows[0] if rows else None