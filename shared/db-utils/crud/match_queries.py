"""Building blocks for the matches table: checking input and writing the SQL.

A match links one user to one internship, with a similarity score. The pair
(user_id, internship_id) is unique, so a user can never be matched to the same
internship twice. match_id is generated, so it can't be set.

similarity_score is stored as a REAL (single precision), so 0.9 comes back as
0.8999999762. Round it when you show it, for example round(score, 2). The code does
not force the score into a range, so the Match Engine can use 0 to 1 or a percent.
"""
import math

import numpy as np

from .internship_queries import check_internship_id
from .resume_queries import check_user_id

MATCH_COLUMNS = ["user_id", "internship_id", "similarity_score"]
MAX_LIMIT = 1000


def check_match_id(match_id):
    """The match id must be a whole number (not text, not True/False). Returns an int."""
    if isinstance(match_id, bool) or not isinstance(match_id, (int, np.integer)):
        raise TypeError("Match ids must be integers.")
    return int(match_id)


def check_score(score):
    """A score must be a finite number, or None (stored as NULL). Returns a float."""
    if score is None:
        return None
    if isinstance(score, bool) or not isinstance(score, (int, float, np.integer, np.floating)):
        raise TypeError("similarity_score must be a number.")
    score = float(score)
    if not math.isfinite(score):
        raise ValueError("similarity_score can't be NaN or infinity.")
    return score


def check_limit(limit):
    """A limit must be a whole number from 1 to MAX_LIMIT."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be a whole number from 1 to {MAX_LIMIT}.")
    return limit


def match_fields(match, for_insert=True, require_score=False):
    """Check a match dict and return its (column, value) pairs.

    for_insert=True requires user_id and internship_id.
    for_insert=False is for updates: only similarity_score may be changed, because the
    pair identifies the match. To move a match to a different pair, delete it and
    create a new one.
    require_score=True is for upserts, where the score is what gets updated."""
    if not isinstance(match, dict):
        raise TypeError("Provide a match record using database column names.")
    for column in match:
        if column not in MATCH_COLUMNS:
            raise ValueError(f"Unsupported match column: {column}")
    if for_insert:
        for column in ("user_id", "internship_id"):
            if column not in match:
                raise ValueError(f"{column} is required.")
    elif "user_id" in match or "internship_id" in match:
        raise ValueError(
            "user_id and internship_id can't be changed. Delete the match and create a new one."
        )
    if require_score and "similarity_score" not in match:
        raise ValueError("similarity_score is required for an upsert.")

    fields = []
    for column in MATCH_COLUMNS:
        if column not in match:
            continue
        value = match[column]
        if column == "user_id":
            value = check_user_id(value)
        elif column == "internship_id":
            value = check_internship_id(value)
        else:
            value = check_score(value)
        fields.append((column, value))
    if not fields:
        raise ValueError("Provide at least one match field.")
    return fields


def _columns_and_placeholders(fields):
    columns = ", ".join(f'"{column}"' for column, _ in fields)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(fields)))
    return columns, placeholders


def insert_query(fields):
    """Build an INSERT that skips the row if this pair already exists.
    RETURNING * gives back the new row, or nothing if the pair was already there."""
    columns, placeholders = _columns_and_placeholders(fields)
    values = [value for _, value in fields]
    return (
        f"INSERT INTO public.matches ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT (user_id, internship_id) DO NOTHING RETURNING *",
        values,
    )


def upsert_query(fields):
    """Build an INSERT that updates the score if this pair already exists."""
    columns, placeholders = _columns_and_placeholders(fields)
    values = [value for _, value in fields]
    return (
        f"INSERT INTO public.matches ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT (user_id, internship_id) DO UPDATE "
        f'SET "similarity_score" = EXCLUDED."similarity_score" RETURNING *',
        values,
    )


def update_assignments(fields):
    """The 'col = $1, col = $2' part of an UPDATE for a list of (column, value) pairs."""
    return ", ".join(f'"{column}" = ${i + 1}' for i, (column, _) in enumerate(fields))