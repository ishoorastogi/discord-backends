"""Building blocks for the internships table: checking input and writing the SQL.

The embedding size comes from resume_queries.py (RESUME_DIM), so resumes and
internships always use the same vector size. If Sai picks a model with a different
size, change RESUME_DIM there and every vector(384) in the schema together.
"""
import numpy as np

from .resume_queries import RESUME_DIM, to_vector

EMBEDDING_DIM = RESUME_DIM

TEXT_COLUMNS = ["company", "title", "description", "location", "role_type", "requirements", "url"]
INTERNSHIP_COLUMNS = TEXT_COLUMNS + ["embedding"]   # id is generated, so it can't be set
REQUIRED_COLUMNS = ["company", "title"]             # NOT NULL in the schema
FILTER_COLUMNS = ["company", "title", "location", "role_type"]
MAX_LIMIT = 1000


def check_internship_id(internship_id):
    """The id must be a whole number (not text, not True/False). Returns it as an int."""
    if isinstance(internship_id, bool) or not isinstance(internship_id, (int, np.integer)):
        raise TypeError("Internship ids must be integers.")
    return int(internship_id)


def check_url(url):
    """A url must be non-empty text. Returns it with spaces trimmed."""
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Provide the internship's url.")
    return url.strip()


def clean_row(row):
    """Turn pgvector Vector values in a row into numpy arrays (query_rows does this
    already; this is for rows read directly inside a transaction)."""
    return {
        key: value.to_numpy() if hasattr(value, "to_numpy") else value
        for key, value in row.items()
    }


def internship_fields(internship, for_insert=True, require_url=False):
    """Check an internship dict and return its (column, value) pairs.

    for_insert=True  requires company and title (they can't be empty in the table).
    for_insert=False is for updates: only the columns given are checked.
    require_url=True is for upserts, where url is how an existing row is found.

    Text is trimmed. Optional text that is blank becomes None (NULL), so blank urls
    can never clash with each other. embedding must be a list or array of exactly
    EMBEDDING_DIM numbers, or None."""
    if not isinstance(internship, dict):
        raise TypeError("Provide an internship record using database column names.")
    for column in internship:
        if column not in INTERNSHIP_COLUMNS:
            raise ValueError(f"Unsupported internship column: {column}")
    if for_insert:
        for column in REQUIRED_COLUMNS:
            if column not in internship:
                raise ValueError(f"{column} is required.")

    fields = []
    for column in INTERNSHIP_COLUMNS:
        if column not in internship:
            continue
        value = internship[column]
        if column == "embedding":
            value = to_vector(value, column)
        elif value is not None:
            if not isinstance(value, str):
                raise TypeError(f"{column} must be text.")
            value = value.strip()
            if value == "" and column not in REQUIRED_COLUMNS:
                value = None
        if column in REQUIRED_COLUMNS and not value:
            raise ValueError(f"{column} can't be empty.")
        fields.append((column, value))

    if require_url and not any(column == "url" and value for column, value in fields):
        raise ValueError("url is required for an upsert.")
    if not fields:
        raise ValueError("Provide at least one internship field.")
    return fields


def _columns_and_placeholders(fields):
    columns = ", ".join(f'"{column}"' for column, _ in fields)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(fields)))
    return columns, placeholders


def insert_query(fields):
    """Build INSERT ... RETURNING * for a list of (column, value) pairs."""
    columns, placeholders = _columns_and_placeholders(fields)
    values = [value for _, value in fields]
    return (
        f"INSERT INTO public.internships ({columns}) VALUES ({placeholders}) RETURNING *",
        values,
    )


def upsert_query(fields):
    """Like insert_query, but if an internship with this url already exists, only the
    columns in `fields` are replaced and the others are kept."""
    columns, placeholders = _columns_and_placeholders(fields)
    values = [value for _, value in fields]
    changed = [column for column, _ in fields if column != "url"]
    set_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in changed)
    return (
        f"INSERT INTO public.internships ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT (url) DO UPDATE SET {set_clause} RETURNING *",
        values,
    )


def select_query(filters=None, limit=100):
    """Build a SELECT for internships matching every filter given.

    filters can use company, title, location, and role_type. Each must match the
    whole value, ignoring case. No filters returns everything, up to `limit`."""
    filters = filters or {}
    if not isinstance(filters, dict):
        raise TypeError("filters must be a dict.")
    for column in filters:
        if column not in FILTER_COLUMNS:
            raise ValueError(f"Can't filter on: {column}")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be a whole number from 1 to {MAX_LIMIT}.")

    conditions, values = [], []
    for column in FILTER_COLUMNS:
        value = filters.get(column)
        if value is None:
            continue
        if not isinstance(value, str):
            raise TypeError(f"{column} filter must be text.")
        values.append(value.strip().lower())
        conditions.append(f'lower("{column}") = ${len(values)}')
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    values.append(limit)
    return f"SELECT * FROM public.internships{where} ORDER BY id LIMIT ${len(values)}", values