"""Insert and upsert for resumes.

A resume is a dict with the user's user_id plus any of the vector columns:
resume_text, skills, experience, education. Each vector is a list or numpy array
of exactly 384 numbers. The user must already exist.

Pass username and password to run as a specific database role. Leave them out
to use the default account from .env.
"""
from db.crud.query import query_rows
from db.crud.resume_queries import insert_query, resume_fields, upsert_query


async def insert_resume(resume, username=None, password=None):
    """Add a resume and return the new row.

    Raises asyncpg.UniqueViolationError if this user already has a resume, and
    asyncpg.ForeignKeyViolationError if the user_id doesn't exist."""
    sql, values = insert_query(resume_fields(resume))
    rows = await query_rows(sql, values, username, password)
    return rows[0]


async def upsert_resume(resume, username=None, password=None):
    """Insert the resume, or update the user's existing one. This is what /resume uses.

    On update, only the columns you pass are replaced; the others keep their old
    values. user_id is the table's primary key, so Postgres makes this one step and
    two calls at once can't create two resumes. Returns the full row."""
    sql, values = upsert_query(resume_fields(resume))
    rows = await query_rows(sql, values, username, password)
    return rows[0]