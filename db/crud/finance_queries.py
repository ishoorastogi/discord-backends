"""Building blocks for the finances table: checking input and writing the SQL.

A finance record has a type ('income', 'expense', or 'dues'), a positive amount, and an
optional user_id (empty for money that doesn't belong to one member). finance_id is
generated, so it can't be set.

Money is handled as exact decimals, never as floats. Pass amounts as Decimal("12.50"),
a text number like "12.50", or a plain number with at most 2 decimal places. A number
like 12.345, or a float sum like 0.1 + 0.2, is rejected on purpose instead of being
silently rounded. Amounts come back from the database as Decimal.

The finances table is locked: only the finance_user role (and the database owner) can
use it. Pass that role's username and password to every function, or leave them out to
use the default account from .env.
"""
import numbers
from decimal import Decimal, InvalidOperation

from db.crud.resume_queries import check_user_id

FINANCE_TYPES = ("income", "expense", "dues")
FINANCE_COLUMNS = ["user_id", "type", "amount"]   # finance_id is generated
FILTER_COLUMNS = ["user_id", "type"]
MAX_AMOUNT = Decimal("99999999.99")               # NUMERIC(10, 2) in the schema
CENT = Decimal("0.01")
MAX_LIMIT = 1000


def check_finance_id(finance_id):
    """The id must be a whole number (not text, not True/False). Returns an int."""
    if isinstance(finance_id, bool) or not isinstance(finance_id, numbers.Integral):
        raise TypeError("Finance ids must be integers.")
    return int(finance_id)


def check_type(value):
    """The type must be 'income', 'expense', or 'dues' (any capitals, extra spaces ignored)."""
    if not isinstance(value, str):
        raise TypeError("type must be text.")
    value = value.strip().lower()
    if value not in FINANCE_TYPES:
        raise ValueError(f"type must be one of: {', '.join(FINANCE_TYPES)}.")
    return value


def check_amount(amount):
    """The amount must be greater than 0, at most 99,999,999.99, with at most 2 decimal
    places. Returns it as a Decimal with exactly 2 decimal places."""
    if isinstance(amount, bool) or not isinstance(amount, (numbers.Real, str, Decimal)):
        raise TypeError("amount must be a number or a text number like '12.50'.")
    try:
        value = amount if isinstance(amount, Decimal) else Decimal(str(amount).strip())
    except InvalidOperation:
        raise ValueError("amount isn't a valid number.")
    if not value.is_finite():
        raise ValueError("amount can't be NaN or infinity.")
    if value <= 0:
        raise ValueError("amount must be greater than 0.")
    if value > MAX_AMOUNT:
        raise ValueError(f"amount can't be more than {MAX_AMOUNT}.")
    if value != value.quantize(CENT):
        raise ValueError("amount can have at most 2 decimal places.")
    return value.quantize(CENT)


def check_limit(limit):
    """A limit must be a whole number from 1 to MAX_LIMIT."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be a whole number from 1 to {MAX_LIMIT}.")
    return limit


def finance_fields(finance, for_insert=True):
    """Check a finance dict and return its (column, value) pairs.

    for_insert=True requires type and amount; user_id is optional.
    for_insert=False is for updates: only the columns given are checked, and at least one
    is needed. user_id can be set to another member, or to None to detach the record."""
    if not isinstance(finance, dict):
        raise TypeError("Provide a finance record using database column names.")
    for column in finance:
        if column not in FINANCE_COLUMNS:
            raise ValueError(f"Unsupported finance column: {column}")
    if for_insert:
        for column in ("type", "amount"):
            if column not in finance:
                raise ValueError(f"{column} is required.")

    fields = []
    for column in FINANCE_COLUMNS:
        if column not in finance:
            continue
        value = finance[column]
        if column == "user_id":
            value = None if value is None else check_user_id(value)
        elif column == "type":
            value = check_type(value)
        else:
            value = check_amount(value)
        fields.append((column, value))
    if not fields:
        raise ValueError("Provide at least one finance field.")
    return fields


def insert_query(fields):
    """Build INSERT ... RETURNING * for a list of (column, value) pairs."""
    columns = ", ".join(f'"{column}"' for column, _ in fields)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(fields)))
    values = [value for _, value in fields]
    return (
        f"INSERT INTO public.finances ({columns}) VALUES ({placeholders}) RETURNING *",
        values,
    )


def update_assignments(fields):
    """The 'col = $1, col = $2' part of an UPDATE for a list of (column, value) pairs."""
    return ", ".join(f'"{column}" = ${i + 1}' for i, (column, _) in enumerate(fields))


def select_query(filters=None, limit=100):
    """Build a SELECT for finance records matching every filter given, newest first.

    filters can use user_id and type. No filters returns everything, up to `limit`."""
    filters = filters or {}
    if not isinstance(filters, dict):
        raise TypeError("filters must be a dict.")
    for column in filters:
        if column not in FILTER_COLUMNS:
            raise ValueError(f"Can't filter on: {column}")
    limit = check_limit(limit)

    conditions, values = [], []
    if filters.get("user_id") is not None:
        values.append(check_user_id(filters["user_id"]))
        conditions.append(f'"user_id" = ${len(values)}')
    if filters.get("type") is not None:
        values.append(check_type(filters["type"]))
        conditions.append(f'"type" = ${len(values)}')
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    values.append(limit)
    return f"SELECT * FROM public.finances{where} ORDER BY finance_id DESC LIMIT ${len(values)}", values


def totals_query(user_id=None):
    """Build a query that adds up the amounts for each type, for one member or for everyone."""
    if user_id is None:
        return 'SELECT "type", SUM("amount") AS total FROM public.finances GROUP BY "type"', []
    return (
        'SELECT "type", SUM("amount") AS total FROM public.finances '
        'WHERE "user_id" = $1 GROUP BY "type"',
        [check_user_id(user_id)],
    )