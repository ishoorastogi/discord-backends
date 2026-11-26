"""Update an existing internship."""
from .internship_queries import check_internship_id, internship_fields
from .query import query_rows


async def update_internship(internship_id, updates, username=None, password=None):
    """Change some columns of an internship and return the updated row.

    `updates` holds only the columns to change, for example {"location": "Austin"}.
    Other columns are left alone. company and title can't be set to empty, and the id
    can't be changed. Returns None if no internship has this id (use upsert_internship
    to create one). Raises asyncpg.UniqueViolationError if the new url is already used
    by another internship."""
    internship_id = check_internship_id(internship_id)
    fields = internship_fields(updates, for_insert=False)
    assignments = ", ".join(f'"{column}" = ${i + 1}' for i, (column, _) in enumerate(fields))
    values = [value for _, value in fields] + [internship_id]
    rows = await query_rows(
        f"UPDATE public.internships SET {assignments} "
        f"WHERE id = ${len(values)} RETURNING *",
        values, username, password,
    )
    return rows[0] if rows else None