"""Look up finance records.

A record comes back as a dict: finance_id, user_id (or None), type, and amount (a
Decimal with 2 decimal places). Lists come back newest first, [] if nothing matches.
"""
from decimal import Decimal

from .finance_queries import (
    FINANCE_TYPES,
    check_finance_id,
    select_query,
    totals_query,
)
from .query import query_rows


async def select_finance_by_id(finance_id, username=None, password=None):
    """The finance record with this id, or None."""
    rows = await query_rows(
        "SELECT * FROM public.finances WHERE finance_id = $1",
        [check_finance_id(finance_id)], username, password,
    )
    return rows[0] if rows else None


async def select_finances(filters=None, limit=100, username=None, password=None):
    """A list of finance records, newest first.

    filters is an optional dict using user_id and/or type, for example
    {"user_id": 5, "type": "dues"}. limit is 1 to 1000 (default 100)."""
    sql, values = select_query(filters, limit)
    return await query_rows(sql, values, username, password)


async def select_finance_totals(user_id=None, username=None, password=None):
    """The total amount for each type, for one member (user_id) or for everyone.

    Returns {"income": Decimal, "expense": Decimal, "dues": Decimal}, with 0.00 for a type
    that has no records. It doesn't combine them: what counts toward a balance is up
    to the caller."""
    sql, values = totals_query(user_id)
    rows = await query_rows(sql, values, username, password)
    totals = {finance_type: Decimal("0.00") for finance_type in FINANCE_TYPES}
    for row in rows:
        totals[row["type"]] = row["total"]
    return totals