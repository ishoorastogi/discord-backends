"""Insert and upsert for internships (one at a time, or a whole batch).

An internship is a dict using the column names: company and title (required),
plus any of description, location, role_type, requirements, url, and embedding.
The embedding is a list or numpy array of exactly 384 numbers.

Pass username and password to run as a specific database role. Leave them out
to use the default account from .env.
"""
from .internship_queries import (
    clean_row,
    insert_query,
    internship_fields,
    upsert_query,
)
from .query import query_rows, with_transaction


async def insert_internship(internship, username=None, password=None):
    """Add one internship and return the new row (including its generated id).

    Raises asyncpg.UniqueViolationError if the url is already in the table."""
    sql, values = insert_query(internship_fields(internship))
    rows = await query_rows(sql, values, username, password)
    return rows[0]


async def upsert_internship(internship, username=None, password=None):
    """Insert the internship, or update the existing one with the same url.

    url, company, and title are required. On update, only the columns you pass are
    replaced; the others keep their old values. url is unique, so Postgres makes this
    one step and two calls at once can't create two rows. Returns the full row."""
    sql, values = upsert_query(internship_fields(internship, require_url=True))
    rows = await query_rows(sql, values, username, password)
    return rows[0]


async def insert_internships(internships, username=None, password=None):
    """Add many internships in one transaction: all are saved, or none are.
    Returns the list of new rows."""
    if not isinstance(internships, list):
        raise TypeError("Provide a list of internships.")
    queries = [insert_query(internship_fields(item)) for item in internships]

    async def work(conn):
        rows = []
        for sql, values in queries:
            rows.append(clean_row(dict(await conn.fetchrow(sql, *values))))
        return rows

    return await with_transaction(work, username, password)


async def upsert_internships(internships, username=None, password=None):
    """Upsert many internships in one transaction: all are saved, or none are.
    This is the call for the GitHub ingestion, where a listing may or may not be
    new. Returns the list of rows."""
    if not isinstance(internships, list):
        raise TypeError("Provide a list of internships.")
    queries = [upsert_query(internship_fields(item, require_url=True)) for item in internships]

    async def work(conn):
        rows = []
        for sql, values in queries:
            rows.append(clean_row(dict(await conn.fetchrow(sql, *values))))
        return rows

    return await with_transaction(work, username, password)