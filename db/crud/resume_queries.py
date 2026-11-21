"""Building blocks for the resumes table: checking input and writing the SQL.

Every resume field is stored as a vector. The numbers below must match the
vector size in schema.sql. 
"""
import numpy as np

RESUME_DIM = 384
VECTOR_COLUMNS = ["resume_text", "skills", "experience", "education"]
RESUME_COLUMNS = set(VECTOR_COLUMNS) | {"user_id"}


def check_user_id(user_id):
    """user_id must be a whole number (not a string, not True/False). Returns it as an int."""
    if isinstance(user_id, bool) or not isinstance(user_id, (int, np.integer)):
        raise TypeError("user_id must be an integer.")
    return int(user_id)


def to_vector(value, column):
    """Check one vector and return it as a float32 numpy array.

    Accepts a list or numpy array of exactly RESUME_DIM numbers, or None (stores NULL)."""
    if value is None:
        return None
    try:
        array = np.asarray(value, dtype=np.float32)
    except (TypeError, ValueError):
        raise TypeError(f"{column} must be a list or array of numbers.")
    if array.ndim != 1 or array.shape[0] != RESUME_DIM:
        raise ValueError(
            f"{column} must be exactly {RESUME_DIM} numbers long (got shape {array.shape})."
        )
    if not np.isfinite(array).all():
        raise ValueError(f"{column} contains NaN or infinity.")
    return array


def resume_fields(resume, require_user_id=True):
    """Check a resume dict and return its (column, value) pairs, user_id first.

    require_user_id=True is for insert and upsert (the dict must include user_id).
    require_user_id=False is for update, where user_id is passed separately and
    can't be changed. At least one vector column is always required."""
    if not isinstance(resume, dict):
        raise TypeError("Provide a resume record using database column names.")
    for column in resume:
        if column not in RESUME_COLUMNS:
            raise ValueError(f"Unsupported resume column: {column}")
    if require_user_id:
        if "user_id" not in resume:
            raise ValueError("Provide the user_id this resume belongs to.")
    elif "user_id" in resume:
        raise ValueError("user_id can't be changed.")
    vectors = [(c, to_vector(resume[c], c)) for c in VECTOR_COLUMNS if c in resume]
    if not vectors:
        raise ValueError("Provide at least one resume field.")
    if require_user_id:
        return [("user_id", check_user_id(resume["user_id"]))] + vectors
    return vectors


def _columns_and_placeholders(fields):
    columns = ", ".join(f'"{column}"' for column, _ in fields)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(fields)))
    return columns, placeholders


def insert_query(fields):
    """Build INSERT ... RETURNING * for a list of (column, value) pairs."""
    columns, placeholders = _columns_and_placeholders(fields)
    values = [value for _, value in fields]
    return (
        f"INSERT INTO public.resumes ({columns}) VALUES ({placeholders}) RETURNING *",
        values,
    )


def upsert_query(fields):
    """Like insert_query, but if this user already has a resume, only the
    columns in `fields` are replaced and the others are kept."""
    columns, placeholders = _columns_and_placeholders(fields)
    values = [value for _, value in fields]
    changed = [column for column, _ in fields if column != "user_id"]
    set_clause = ", ".join(f'"{c}" = EXCLUDED."{c}"' for c in changed)
    return (
        f"INSERT INTO public.resumes ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT (user_id) DO UPDATE SET {set_clause} RETURNING *",
        values,
    )