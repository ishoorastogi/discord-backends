"""Python version of userQueries.js (ported from the original Node.js file).

Builds the SQL for the users table, checks which columns a caller may set,
and finds members by name or nickname.
"""

# Columns a caller is allowed to set. Column names are inserted into SQL text,
# so only names from this set are ever used (never text from a caller).
USER_COLUMNS = {
    "discord_id", "name", "email", "phone", "class", "major", "grad_year",
    "positions_held", "family_line", "nicknames", "brotherhood_status",
    "linkedin_link", "big", "littles", "employer",
}


class AmbiguousUserError(Exception):
    """More than one member matched the name. `options` lists the matching names."""
    code = "AMBIGUOUS_USER"

    def __init__(self, message, options=None):
        super().__init__(message)
        self.options = options or []


class MemberChangedError(Exception):
    """The member's record changed after the caller confirmed it."""
    code = "MEMBER_CHANGED"


def normalize_name(name):
    """Trim and collapse repeated spaces: '  Alex   Smith ' -> 'Alex Smith'."""
    return " ".join(name.split())


def user_fields(user):
    """Check a user dict and return its (column, value) pairs.

    Raises if it isn't a dict, has a column that isn't allowed, is empty,
    or has a discord_id that isn't a string."""
    if not isinstance(user, dict):
        raise TypeError("Provide a user record using database column names.")
    for column in user:
        if column not in USER_COLUMNS:
            raise ValueError(f"Unsupported user column: {column}")
    fields = list(user.items())
    if not fields:
        raise ValueError("Provide at least one user field.")
    discord_id = user.get("discord_id")
    if discord_id is not None and not isinstance(discord_id, str):
        raise TypeError("Discord IDs must be strings to preserve their digits.")
    return fields


def insert_query(fields):
    """Build INSERT ... RETURNING * for a list of (column, value) pairs."""
    columns = ", ".join(f'"{column}"' for column, _ in fields)
    placeholders = ", ".join(f"${i + 1}" for i in range(len(fields)))
    values = [value for _, value in fields]
    sql = f"INSERT INTO public.users ({columns}) VALUES ({placeholders}) RETURNING *"
    return sql, values


def _normalized_sql(expression):
    """SQL that lowercases, trims, and collapses repeated spaces in a column."""
    return rf"LOWER(BTRIM(regexp_replace(COALESCE({expression}, ''), '\s+', ' ', 'g')))"


def matching_users_query(name, mode="exact"):
    """Find members by name. Case-insensitive, ignores extra spaces.

    exact:  the full name matches.
    prefix: the name starts with the text.
    lookup: the text appears anywhere in the name, or matches a nickname.

    In every mode, an exact full-name match wins: other candidates are only
    returned when nobody matches the full name exactly."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Provide a name or nickname.")
    value = normalize_name(name).lower()
    normalized_name = _normalized_sql("name")

    predicate = f"{normalized_name} = $1"
    if mode == "prefix":
        predicate = f"strpos({normalized_name}, $1) = 1"
    if mode == "lookup":
        predicate = rf"""strpos({normalized_name}, $1) > 0 OR {_normalized_sql("nicknames")} = $1 OR EXISTS (
            SELECT 1 FROM regexp_split_to_table(COALESCE(nicknames, ''), '[,;\r\n]+') AS nickname(value)
            WHERE strpos({_normalized_sql("nickname.value")}, $1) > 0
        )"""

    sql = f"""WITH candidates AS (SELECT * FROM public.users WHERE {predicate})
        SELECT * FROM candidates WHERE {normalized_name} = $1
            OR NOT EXISTS (SELECT 1 FROM candidates WHERE {normalized_name} = $1)
        ORDER BY user_id"""
    return sql, [value]


def unique_user(rows):
    """Return the single matching row, None if there are none, or raise if several."""
    if len(rows) > 1:
        names = list(dict.fromkeys(row["name"] for row in rows))
        raise AmbiguousUserError(
            "More than one member matches that name. Use a unique full name or nickname.",
            options=names,
        )
    return rows[0] if rows else None