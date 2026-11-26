"""Correct an existing finance record."""
from db.crud.finance_queries import (
    check_finance_id,
    finance_fields,
    update_assignments,
)
from db.crud.query import query_rows


async def update_finance(finance_id, updates, username=None, password=None):
    """Change some columns of a finance record and return the updated row.

    `updates` holds only the columns to change, for example {"amount": "175.00"}. The
    type, amount, and user_id can all be corrected; user_id can be set to None to detach
    the record from a member. Returns None if there is no record with this id.
    Raises asyncpg.ForeignKeyViolationError if the new user_id doesn't exist."""
    finance_id = check_finance_id(finance_id)
    fields = finance_fields(updates, for_insert=False)
    values = [value for _, value in fields] + [finance_id]
    rows = await query_rows(
        f"UPDATE public.finances SET {update_assignments(fields)} "
        f"WHERE finance_id = ${len(values)} RETURNING *",
        values, username, password,
    )
    return rows[0] if rows else None