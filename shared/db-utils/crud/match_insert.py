"""Insert and upsert for matches.

A match is a dict with user_id and internship_id (both required) and an optional
similarity_score. The user and the internship must already exist.

Pass username and password to run as a specific database role. Leave them out
to use the default account from .env.
"""
from .match_queries import insert_query, match_fields, upsert_query
from .query import query_rows, with_transaction


async def insert_match(match, username=None, password=None):
    """Create a match and return the new row (including its generated match_id).

    If this user was already matched to this internship, nothing is inserted and None
    is returned. That is the Match Engine's 'check match history' step: None means
    'already matched, don't notify again'. Raises asyncpg.ForeignKeyViolationError if
    the user or the internship doesn't exist."""
    sql, values = insert_query(match_fields(match))
    rows = await query_rows(sql, values, username, password)
    return rows[0] if rows else None


async def insert_matches(matches, username=None, password=None):
    """Create many matches in one transaction: all are processed, or none are.

    Pairs that already exist are skipped. Returns a list with only the NEWLY created
    matches, which is the list of people the bot should notify. If any row is invalid
    or points at a user or internship that doesn't exist, nothing is saved."""
    if not isinstance(matches, list):
        raise TypeError("Provide a list of matches.")
    queries = [insert_query(match_fields(match)) for match in matches]

    async def work(conn):
        created = []
        for sql, values in queries:
            row = await conn.fetchrow(sql, *values)
            if row is not None:
                created.append(dict(row))
        return created

    return await with_transaction(work, username, password)


async def upsert_match(match, username=None, password=None):
    """Create the match, or update the score if this pair already exists.

    similarity_score is required (it can be None). The pair is unique, so Postgres makes
    this one step and two calls at once can't create two matches. Returns the full row."""
    sql, values = upsert_query(match_fields(match, require_score=True))
    rows = await query_rows(sql, values, username, password)
    return rows[0]