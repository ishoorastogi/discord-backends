"""Checks the five user files against a real database:
user_queries, user_insert, user_update, user_delete, and user_select.

Run from the repo root (the folder that contains db/):
    python -m db.test_crud

It creates rows named "Test ..." / "test-..." and removes them again at the end.
To also test database roles, set these in your environment (or .env) first:
    BROTHERHOOD_BOT_PASSWORD, FINANCE_USER_PASSWORD
"""
import asyncio
import os
import sys

import asyncpg

from crud import Connection
from crud.query import query_rows
from crud.user_delete import delete_user_by_name
from crud.user_insert import insert_user, insert_users, upsert_user
from crud.user_queries import (
    AmbiguousUserError,
    MemberChangedError,
    insert_query,
    matching_users_query,
    unique_user,
    user_fields,
)
from crud.user_select import (
    select_user_by_discord_id,
    select_user_by_id,
    select_users_by_name,
    select_users_by_name_or_nickname,
)
from crud.user_update import update_user_by_name

failures = []


def check(label, condition):
    print(("PASS  " if condition else "FAIL  ") + label)
    if not condition:
        failures.append(label)


def raises(label, exception, func):
    """Check that calling func() raises the given exception."""
    try:
        func()
    except exception:
        check(label, True)
    else:
        check(label, False)


async def count(sql, *args):
    async with Connection.get_pool().acquire() as conn:
        return await conn.fetchval(sql, *args)


async def cleanup():
    async with Connection.get_pool().acquire() as conn:
        await conn.execute("DELETE FROM users WHERE discord_id LIKE 'test-%' OR name LIKE 'Test %'")


def test_user_queries():
    print("\n--- user_queries (no database needed) ---")
    check("user_fields keeps the pairs in order",
          user_fields({"name": "Alex", "major": "CS"}) == [("name", "Alex"), ("major", "CS")])
    raises("user_fields rejects an unknown column", ValueError, lambda: user_fields({"bogus": 1}))
    raises("user_fields rejects an empty record", ValueError, lambda: user_fields({}))
    raises("user_fields rejects a non-string discord_id", TypeError, lambda: user_fields({"discord_id": 123}))
    raises("user_fields rejects a non-dict", TypeError, lambda: user_fields(["name"]))
    sql, values = insert_query([("name", "Alex"), ("major", "CS")])
    check("insert_query builds the INSERT with placeholders",
          sql == 'INSERT INTO public.users ("name", "major") VALUES ($1, $2) RETURNING *')
    check("insert_query returns the values in order", values == ["Alex", "CS"])
    raises("matching_users_query rejects a blank name", ValueError, lambda: matching_users_query("   "))
    check("matching_users_query cleans up the name",
          matching_users_query("  Alex   Smith ")[1] == ["alex smith"])
    check("unique_user returns None for no rows", unique_user([]) is None)
    check("unique_user returns the one row", unique_user([{"name": "A"}]) == {"name": "A"})
    try:
        unique_user([{"name": "A"}, {"name": "A"}, {"name": "B"}])
        check("unique_user raises for several rows", False)
    except AmbiguousUserError as err:
        check("unique_user raises for several rows, listing each name once", err.options == ["A", "B"])


async def main():
    test_user_queries()

    await Connection.init_pool()
    await cleanup()

    print("\n--- user_insert: insert_user and insert_users ---")
    alpha = await insert_user({"discord_id": "test-1", "name": "Test Alpha", "major": "CS"})
    check("insert_user returns the new row", alpha["user_id"] is not None and alpha["name"] == "Test Alpha")
    try:
        await insert_user({"discord_id": "test-1", "name": "Test Dupe"})
        check("insert_user rejects a duplicate discord_id", False)
    except asyncpg.UniqueViolationError:
        check("insert_user rejects a duplicate discord_id", True)
    bravo = await insert_user({"name": "Test Bravo", "email": "b@x.com", "littles": ["Test Charlie"]})
    check("insert_user stores a list column", bravo["littles"] == ["Test Charlie"])
    many = await insert_users([{"name": "Test Delta"}, {"name": "Test Echo One"}, {"name": "Test Echo Two"}])
    check("insert_users adds every row", len(many) == 3)
    try:
        await insert_users([{"name": "Test Good"}, {"discord_id": "test-1", "name": "Test Dupe"}])
        check("insert_users saves nothing if one row fails", False)
    except asyncpg.UniqueViolationError:
        check("insert_users saves nothing if one row fails",
              await count("SELECT count(*) FROM users WHERE name = 'Test Good'") == 0)
    try:
        await insert_users({"name": "Test Nope"})
        check("insert_users rejects a non-list", False)
    except TypeError:
        check("insert_users rejects a non-list", True)

    print("\n--- user_insert: upsert_user ---")
    up = await upsert_user({"name": "test   bravo", "phone": "555-0100"})
    check("upsert finds the member despite case and spaces", up["user_id"] == bravo["user_id"])
    check("upsert keeps old columns and sets new ones", up["phone"] == "555-0100" and up["email"] == "b@x.com")
    check("upsert did not create a second Bravo",
          await count("SELECT count(*) FROM users WHERE name ILIKE 'test bravo'") == 1)
    new = await upsert_user({"name": "Test Foxtrot", "major": "Art"})
    check("upsert creates a member when none matches", new["user_id"] != bravo["user_id"] and new["major"] == "Art")
    same = await upsert_user({"name": "Test Foxtrot"})
    check("upsert with only a name returns the existing member", same["user_id"] == new["user_id"])
    try:
        await upsert_user({"major": "Bio"})
        check("upsert requires a name", False)
    except ValueError:
        check("upsert requires a name", True)
    try:
        await upsert_user({"bogus": 1, "name": "Test Hotel"})
        check("upsert rejects an unknown column", False)
    except ValueError:
        check("upsert rejects an unknown column", True)
    echo = await upsert_user({"name": "Test Echo", "major": "X"})
    check("upsert does not match a name prefix, it creates its own member",
          echo["name"] == "Test Echo" and echo["user_id"] not in [m["user_id"] for m in many])
    check("Echo One and Echo Two were left alone",
          await count("SELECT count(*) FROM users WHERE name IN ('Test Echo One', 'Test Echo Two') AND major IS NULL") == 2)

    print("\n--- user_update ---")
    upd = await update_user_by_name("Test Br", {"major": "Bio"})
    check("update finds a member by unique name prefix",
          not upd["created"] and upd["user"]["user_id"] == bravo["user_id"])
    check("update reports the changed columns", upd["updated_columns"] == ["major"] and upd["user"]["major"] == "Bio")
    made = await update_user_by_name("Test Golf", {"major": "Law"})
    check("update creates the member when none matches", made["created"] and made["user"]["name"] == "Test Golf")
    clash = await update_user_by_name("Test Bravo", {"name": "Test Delta", "major": "Chem"})
    check("rename to a taken name is refused",
          bool(clash["errors"]) and clash["errors"][0]["code"] == "AMBIGUOUS_USER")
    check("the other updates in that call still apply",
          clash["user"]["major"] == "Chem" and clash["user"]["name"] == "Test Bravo")
    renamed = await update_user_by_name("Test Golf", {"name": "Test Gulf"})
    check("rename to a free name works", renamed["user"]["name"] == "Test Gulf" and not renamed["errors"])
    try:
        await update_user_by_name("Test Ech", {"major": "X"})
        check("update raises when the prefix matches several members", False)
    except AmbiguousUserError as err:
        check("update raises when the prefix matches several members, listing them",
              sorted(err.options) == ["Test Echo", "Test Echo One", "Test Echo Two"])
    try:
        await update_user_by_name("Test Bravo", {})
        check("update rejects an empty update", False)
    except ValueError:
        check("update rejects an empty update", True)

    print("\n--- user_select ---")
    by_discord = await select_user_by_discord_id("test-1")
    check("select by discord id", by_discord is not None and by_discord["name"] == "Test Alpha")
    check("select by discord id returns None when missing", await select_user_by_discord_id("test-nobody") is None)
    by_id = await select_user_by_id(alpha["user_id"])
    check("select by user id", by_id is not None and by_id["discord_id"] == "test-1")
    check("select by user id returns None when missing", await select_user_by_id(999999999) is None)
    check("select by name ignores case and extra spaces",
          [r["name"] for r in await select_users_by_name("  test   ALPHA ")] == ["Test Alpha"])
    check("select by name returns [] when nobody matches", await select_users_by_name("Test Nobody") == [])
    await upsert_user({"name": "Test Juliet", "nicknames": "JJ, Jules; The Juice"})
    check("lookup by nickname",
          [r["name"] for r in await select_users_by_name_or_nickname("jules")] == ["Test Juliet"])
    check("lookup by part of a name",
          "Test Juliet" in [r["name"] for r in await select_users_by_name_or_nickname("julie")])
    check("exact full name wins in lookup",
          [r["name"] for r in await select_users_by_name_or_nickname("test echo one")] == ["Test Echo One"])

    print("\n--- user_delete ---")
    stale = {**(await query_rows("SELECT * FROM users WHERE name = 'Test Bravo'"))[0], "major": "Old"}
    try:
        await delete_user_by_name("Test Bravo", stale)
        check("delete refuses a record that changed", False)
    except MemberChangedError:
        check("delete refuses a record that changed, and deletes nothing",
              await count("SELECT count(*) FROM users WHERE name = 'Test Bravo'") == 1)
    current = (await query_rows("SELECT * FROM users WHERE name = 'Test Bravo'"))[0]
    gone = await delete_user_by_name("Test Bravo", current)
    check("delete removes the member and returns the row", gone["user_id"] == bravo["user_id"])
    check("the member is really gone", await count("SELECT count(*) FROM users WHERE name = 'Test Bravo'") == 0)
    check("delete returns None when nobody matches", await delete_user_by_name("Test Bravo") is None)
    plain = await delete_user_by_name("Test Foxtrot")
    check("delete works without a confirmation record", plain is not None and plain["name"] == "Test Foxtrot")

    bot_pw = os.getenv("BROTHERHOOD_BOT_PASSWORD")
    fin_pw = os.getenv("FINANCE_USER_PASSWORD")
    if bot_pw and fin_pw:
        print("\n--- database roles ---")
        row = await insert_user({"name": "Test Role Member"}, "brotherhood_bot", bot_pw)
        check("brotherhood_bot can insert users", row["user_id"] is not None)
        up_row = await upsert_user({"name": "Test Role Member", "major": "CS"}, "brotherhood_bot", bot_pw)
        check("brotherhood_bot can upsert users", up_row["major"] == "CS")
        upd_row = await update_user_by_name("Test Role", {"major": "Math"}, "brotherhood_bot", bot_pw)
        check("brotherhood_bot can update users", upd_row["user"]["major"] == "Math")
        found = await select_users_by_name("Test Role Member", "brotherhood_bot", bot_pw)
        check("brotherhood_bot can select users", len(found) == 1)
        deleted = await delete_user_by_name("Test Role Member", None, "brotherhood_bot", bot_pw)
        check("brotherhood_bot can delete users", deleted is not None)
        bot_pool = await Connection.get_role_pool("brotherhood_bot", bot_pw)
        try:
            async with bot_pool.acquire() as conn:
                await conn.fetch("SELECT * FROM finances")
            check("brotherhood_bot is blocked from finances", False)
        except asyncpg.InsufficientPrivilegeError:
            check("brotherhood_bot is blocked from finances", True)
        fin_rows = await select_users_by_name("Test Alpha", "finance_user", fin_pw)
        check("finance_user can read users", len(fin_rows) == 1)
        try:
            await insert_user({"name": "Test Nope"}, "finance_user", fin_pw)
            check("finance_user is blocked from writing users", False)
        except asyncpg.InsufficientPrivilegeError:
            check("finance_user is blocked from writing users", True)
    else:
        print("\n(skipping role tests: set BROTHERHOOD_BOT_PASSWORD and FINANCE_USER_PASSWORD to run them)")

    await cleanup()
    await Connection.close_pool()
    print(f"\n{'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' CHECK(S) FAILED'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    asyncio.run(main())