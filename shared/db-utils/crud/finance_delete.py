"""Delete finance records.

Deleting is permanent. Financial records are usually kept for bookkeeping, so
prefer update_finance to correct a mistake, and delete only to remove a record that
should never have existed.
"""
from .finance_queries import check_finance_id
from .query import query_rows


async def delete_finance(finance_id, username=None, password=None):
    """Delete the finance record with this id and return the deleted row, or None."""
    rows = await query_rows(
        "DELETE FROM public.finances WHERE finance_id = $1 RETURNING *",
        [check_finance_id(finance_id)], username, password,
    )
    return rows[0] if rows else None