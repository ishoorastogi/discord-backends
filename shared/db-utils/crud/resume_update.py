"""Update an existing resume."""
from .query import query_rows
from .resume_queries import check_user_id, resume_fields


async def update_resume(user_id, updates, username=None, password=None):
    """Change some columns of a user's resume and return the updated row.

    `updates` holds only the vector columns to change, for example
    {"skills_vector": [...384 numbers...]}. Other columns are left alone. Returns None
    if this user has no resume (use upsert_resume to create one).
    user_id can't be changed, so it must not be inside `updates`."""
    user_id = check_user_id(user_id)
    fields = resume_fields(updates, require_user_id=False)
    assignments = ", ".join(f'"{column}" = ${i + 1}' for i, (column, _) in enumerate(fields))
    values = [value for _, value in fields] + [user_id]
    rows = await query_rows(
        f"UPDATE public.resumes SET {assignments} "
        f"WHERE user_id = ${len(values)} RETURNING *",
        values, username, password,
    )
    return rows[0] if rows else None
