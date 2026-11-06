"""Connect using the shared database settings and internship credentials."""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


ENV_FILE = Path(__file__).resolve().parents[1] / "src" / ".env"
DB_ENV_FILE = Path(__file__).resolve().parents[2] / "shared" / "db-utils" / ".env"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "discord_id",
        nargs="?",
        help="Discord ID to read (default: first user ordered by Discord ID)",
    )
    args = parser.parse_args()

    for env_file, required in (
        (DB_ENV_FILE, ("DB_HOST", "DB_PORT", "DB_NAME")),
        (ENV_FILE, ("DB_USER", "DB_PASSWORD")),
    ):
        load_dotenv(env_file, override=False)
        missing = [key for key in required if not os.getenv(key)]
        if missing:
            parser.error(f"Set {', '.join(missing)} in {env_file} or your environment")

    try:
        port = int(os.environ["DB_PORT"])
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        parser.error("DB_PORT must be an integer between 1 and 65535")

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        print(
            'Install the database driver: python3 -m pip install "psycopg[binary]>=3.1,<4"',
            file=sys.stderr,
        )
        return 1

    try:
        with psycopg.connect(
            host=os.environ["DB_HOST"],
            port=port,
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            connect_timeout=5,
            row_factory=dict_row,
        ) as connection:
            connection.read_only = True
            with connection.cursor() as cursor:
                query = (
                    "SELECT discord_id, name, major, grad_year, phone, email, employer "
                    "FROM public.users "
                )
                if args.discord_id is not None:
                    cursor.execute(query + "WHERE discord_id = %s", (args.discord_id,))
                else:
                    cursor.execute(query + "ORDER BY discord_id LIMIT 1")
                user = cursor.fetchone()
    except psycopg.Error as exc:
        print(f"Could not read user from PostgreSQL: {exc}", file=sys.stderr)
        return 1

    if user is None:
        message = (
            f"No user found for Discord ID {args.discord_id}."
            if args.discord_id is not None
            else "Connected successfully, but the users table is empty."
        )
        print(message, file=sys.stderr)
        return 1

    print(json.dumps(user, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
