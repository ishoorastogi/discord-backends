"""Checks the match files against a real database:
match_queries, match_insert, match_update, match_select, and match_delete.

Run from the repository root:
    python -m shared.db-utils.crud.test_match

It creates members named "Test Match ...", internships with urls starting
https://example.com/test-match, and matches between them, and removes them all at the end.
"""
import asyncio
import sys

import asyncpg

from . import Connection as connection
from .internship_insert import insert_internship
from .match_delete import delete_match, delete_match_by_pair
from .match_insert import insert_match, insert_matches, upsert_match
from .match_queries import (
    check_limit,
    check_match_id,
    check_score,
    insert_query,
    match_fields,
    upsert_query,
)
from .match_select import (
    match_exists,
    select_match_by_id,
    select_match_by_pair,
    select_match_details,
    select_matches_for_internship,
    select_matches_for_user,
)
from .match_update import update_match, update_match_by_pair
from .user_insert import insert_user

failures = []


def approx(a, b):
    return a is not None and abs(a - b) < 1e-5


def check(label, condition):
    print(("PASS  " if condition else "FAIL  ") + label)
    if not condition:
        failures.append(label)


def raises(label, exception, func):
    try:
        func()
    except exception:
        check(label, True)
    else:
        check(label, False)


async def expect(label, exception, coroutine):
    try:
        await coroutine
    except exception:
        check(label, True)
    else:
        check(label, False)


async def count(sql, *args):
    async with connection.get_pool().acquire() as conn:
        return await conn.fetchval(sql, *args)


async def cleanup():
    async with connection.get_pool().acquire() as conn:
        await conn.execute("DELETE FROM users WHERE discord_id LIKE 'test-m%' OR name LIKE 'Test Match %'")
        await conn.execute("DELETE FROM internships WHERE url LIKE 'https://example.com/test-match%'")


def test_match_queries():
    print("\n--- match_queries (no database needed) ---")
    fields = match_fields({"user_id": 1, "internship_id": 2, "similarity_score": 3})
    check("match_fields keeps the pairs in order",
          fields == [("user_id", 1), ("internship_id", 2), ("similarity_score", 3.0)])
    check("an int score becomes a float", isinstance(fields[2][1], float))
    check("a missing score is fine", match_fields({"user_id": 1, "internship_id": 2}) == [("user_id", 1), ("internship_id", 2)])
    check("a score of None is kept (stores NULL)", match_fields({"user_id": 1, "internship_id": 2, "similarity_score": None})[2] == ("similarity_score", None))
    raises("rejects an unknown column", ValueError, lambda: match_fields({"user_id": 1, "internship_id": 2, "bogus": 1}))
    raises("rejects match_id (it is generated)", ValueError, lambda: match_fields({"match_id": 5, "user_id": 1, "internship_id": 2}))
    raises("rejects a missing user_id", ValueError, lambda: match_fields({"internship_id": 2}))
    raises("rejects a missing internship_id", ValueError, lambda: match_fields({"user_id": 1}))
    raises("rejects a text user_id", TypeError, lambda: match_fields({"user_id": "1", "internship_id": 2}))
    raises("rejects True as an internship_id", TypeError, lambda: match_fields({"user_id": 1, "internship_id": True}))
    raises("rejects a text score", TypeError, lambda: match_fields({"user_id": 1, "internship_id": 2, "similarity_score": "0.9"}))
    raises("rejects True as a score", TypeError, lambda: match_fields({"user_id": 1, "internship_id": 2, "similarity_score": True}))
    raises("rejects a NaN score", ValueError, lambda: match_fields({"user_id": 1, "internship_id": 2, "similarity_score": float("nan")}))
    raises("rejects an infinite score", ValueError, lambda: match_fields({"user_id": 1, "internship_id": 2, "similarity_score": float("inf")}))
    raises("rejects a non-dict", TypeError, lambda: match_fields([1, 2]))
    raises("rejects an empty update", ValueError, lambda: match_fields({}, for_insert=False))
    check("update fields accept just a score", match_fields({"similarity_score": 0.5}, for_insert=False) == [("similarity_score", 0.5)])
    raises("update fields reject user_id", ValueError, lambda: match_fields({"user_id": 1, "similarity_score": 0.5}, for_insert=False))
    raises("update fields reject internship_id", ValueError, lambda: match_fields({"internship_id": 1}, for_insert=False))
    raises("upsert requires a score", ValueError, lambda: match_fields({"user_id": 1, "internship_id": 2}, require_score=True))
    check("upsert accepts a score of None", match_fields({"user_id": 1, "internship_id": 2, "similarity_score": None}, require_score=True)[2][1] is None)
    raises("rejects True as a match id", TypeError, lambda: check_match_id(True))
    raises("rejects a text match id", TypeError, lambda: check_match_id("5"))
    raises("rejects a limit of 0", ValueError, lambda: check_limit(0))
    raises("rejects a limit that's too big", ValueError, lambda: check_limit(5000))
    raises("rejects True as a limit", ValueError, lambda: check_limit(True))
    check("check_score(None) is None", check_score(None) is None)
    sql, values = insert_query([("user_id", 1), ("internship_id", 2)])
    check("insert_query skips existing pairs",
          sql == 'INSERT INTO public.matches ("user_id", "internship_id") VALUES ($1, $2) '
                 'ON CONFLICT (user_id, internship_id) DO NOTHING RETURNING *' and values == [1, 2])
    sql, _ = upsert_query([("user_id", 1), ("internship_id", 2), ("similarity_score", 0.5)])
    check("upsert_query updates only the score", 'DO UPDATE SET "similarity_score" = EXCLUDED."similarity_score"' in sql)


async def main():
    test_match_queries()

    await connection.init_pool()
    await cleanup()

    u1 = (await insert_user({"discord_id": "test-m1", "name": "Test Match One"}))["user_id"]
    u2 = (await insert_user({"discord_id": "test-m2", "name": "Test Match Two"}))["user_id"]
    u3 = (await insert_user({"discord_id": "test-m3", "name": "Test Match Three"}))["user_id"]
    i1 = (await insert_internship({"company": "TestCo", "title": "Test Match Intern 1", "url": "https://example.com/test-match-1"}))["id"]
    i2 = (await insert_internship({"company": "TestCo", "title": "Test Match Intern 2", "url": "https://example.com/test-match-2"}))["id"]
    i3 = (await insert_internship({"company": "OtherCo", "title": "Test Match Intern 3", "url": "https://example.com/test-match-3"}))["id"]

    print("\n--- match_insert: insert_match ---")
    first = await insert_match({"user_id": u1, "internship_id": i1, "similarity_score": 0.9})
    check("insert_match returns the new row with a match_id",
          first is not None and isinstance(first["match_id"], int) and first["user_id"] == u1 and first["internship_id"] == i1)
    check("the score is stored", approx(first["similarity_score"], 0.9))
    again = await insert_match({"user_id": u1, "internship_id": i1, "similarity_score": 0.1})
    check("a second insert for the same pair returns None", again is None)
    check("...and creates no second row", await count("SELECT count(*) FROM matches WHERE user_id = $1 AND internship_id = $2", u1, i1) == 1)
    check("...and leaves the original score alone",
          approx(await count("SELECT similarity_score FROM matches WHERE match_id = $1", first["match_id"]), 0.9))
    no_score = await insert_match({"user_id": u2, "internship_id": i1})
    check("a match without a score stores NULL", no_score is not None and no_score["similarity_score"] is None)
    await expect("insert rejects a user that doesn't exist", asyncpg.ForeignKeyViolationError,
                 insert_match({"user_id": 999999999, "internship_id": i1, "similarity_score": 0.5}))
    await expect("insert rejects an internship that doesn't exist", asyncpg.ForeignKeyViolationError,
                 insert_match({"user_id": u1, "internship_id": 999999999, "similarity_score": 0.5}))
    await expect("insert requires an internship_id", ValueError, insert_match({"user_id": u1}))
    await expect("insert rejects a text user_id", TypeError, insert_match({"user_id": str(u1), "internship_id": i1}))
    await expect("insert rejects an unknown column", ValueError, insert_match({"user_id": u1, "internship_id": i2, "bogus": 1}))

    print("\n--- match_insert: insert_matches ---")
    created = await insert_matches([
        {"user_id": u1, "internship_id": i2, "similarity_score": 0.8},
        {"user_id": u1, "internship_id": i1, "similarity_score": 0.7},
    ])
    check("insert_matches returns only the newly created matches",
          len(created) == 1 and created[0]["internship_id"] == i2)
    check("the existing pair was skipped, not changed",
          approx(await count("SELECT similarity_score FROM matches WHERE user_id = $1 AND internship_id = $2", u1, i1), 0.9))
    await expect("insert_matches saves nothing if one row fails", asyncpg.ForeignKeyViolationError,
                 insert_matches([
                     {"user_id": u2, "internship_id": i2, "similarity_score": 0.6},
                     {"user_id": 999999999, "internship_id": i1, "similarity_score": 0.6},
                 ]))
    check("...so the good row wasn't saved either",
          await count("SELECT count(*) FROM matches WHERE user_id = $1 AND internship_id = $2", u2, i2) == 0)
    await expect("insert_matches rejects a non-list", TypeError, insert_matches({"user_id": u1, "internship_id": i1}))
    check("insert_matches accepts an empty list", await insert_matches([]) == [])

    print("\n--- match_insert: upsert_match ---")
    up = await upsert_match({"user_id": u1, "internship_id": i1, "similarity_score": 0.95})
    check("upsert updates the score of an existing pair",
          up["match_id"] == first["match_id"] and approx(up["similarity_score"], 0.95))
    check("upsert did not create a second row",
          await count("SELECT count(*) FROM matches WHERE user_id = $1 AND internship_id = $2", u1, i1) == 1)
    cleared = await upsert_match({"user_id": u1, "internship_id": i1, "similarity_score": None})
    check("upsert can set the score to NULL", cleared["similarity_score"] is None)
    new = await upsert_match({"user_id": u3, "internship_id": i1, "similarity_score": 0.5})
    check("upsert creates the match when the pair is new", new["match_id"] != first["match_id"] and approx(new["similarity_score"], 0.5))
    await expect("upsert requires a score", ValueError, upsert_match({"user_id": u3, "internship_id": i2}))
    await expect("upsert rejects a user that doesn't exist", asyncpg.ForeignKeyViolationError,
                 upsert_match({"user_id": 999999999, "internship_id": i1, "similarity_score": 0.5}))
    results = await asyncio.gather(*[
        upsert_match({"user_id": u3, "internship_id": i3, "similarity_score": i / 10}) for i in range(10)
    ])
    check("10 simultaneous upserts leave exactly one match",
          len(results) == 10 and await count("SELECT count(*) FROM matches WHERE user_id = $1 AND internship_id = $2", u3, i3) == 1)

    print("\n--- match_update ---")
    upd = await update_match(first["match_id"], {"similarity_score": 0.77})
    assert upd is not None
    check("update_match changes the score", approx(upd["similarity_score"], 0.77))
    check("update_match leaves the pair alone", upd["user_id"] == u1 and upd["internship_id"] == i1)
    upd2 = await update_match_by_pair(u1, i1, {"similarity_score": 0.66})
    assert upd2 is not None
    check("update_match_by_pair finds the match by user and internship", upd2["match_id"] == first["match_id"] and approx(upd2["similarity_score"], 0.66))
    check("update_match returns None when the id doesn't exist", await update_match(999999999, {"similarity_score": 0.1}) is None)
    check("update_match_by_pair returns None when they weren't matched",
          await update_match_by_pair(u2, i3, {"similarity_score": 0.1}) is None)
    await expect("update rejects an empty update", ValueError, update_match(first["match_id"], {}))
    await expect("update can't change the user", ValueError, update_match(first["match_id"], {"user_id": u2}))
    await expect("update can't change the internship", ValueError, update_match_by_pair(u1, i1, {"internship_id": i2}))
    await expect("update rejects a text score", TypeError, update_match(first["match_id"], {"similarity_score": "high"}))
    await expect("update rejects a text id", TypeError, update_match(str(first["match_id"]), {"similarity_score": 0.5}))

    print("\n--- match_select ---")
    got = await select_match_by_id(first["match_id"])
    check("select by match_id", got is not None and got["user_id"] == u1)
    check("select by match_id returns None when missing", await select_match_by_id(999999999) is None)
    pair = await select_match_by_pair(u1, i1)
    check("select by pair", pair is not None and pair["match_id"] == first["match_id"])
    check("select by pair returns None when they weren't matched", await select_match_by_pair(u2, i3) is None)
    check("match_exists is True for a matched pair", await match_exists(u1, i1) is True)
    check("match_exists is False for an unmatched pair", await match_exists(u2, i3) is False)
    await expect("match_exists rejects a text id", TypeError, match_exists(str(u1), i1))

    # u3 now has three matches: i1 (0.5), i3 (0.9), and one more with no score
    await upsert_match({"user_id": u3, "internship_id": i3, "similarity_score": 0.9})
    await upsert_match({"user_id": u3, "internship_id": i2, "similarity_score": None})
    for_user = await select_matches_for_user(u3)
    check("a user's matches come back best score first, no score last",
          [m["internship_id"] for m in for_user] == [i3, i1, i2])
    check("the limit caps a user's matches", len(await select_matches_for_user(u3, limit=2)) == 2)
    check("a user with no matches gets []", await select_matches_for_user(999999999) == [])
    for_internship = await select_matches_for_internship(i1)
    check("an internship's matches include every matched user",
          sorted(m["user_id"] for m in for_internship) == sorted([u1, u2, u3]))
    check("an internship's matches are best score first",
          [m["user_id"] for m in for_internship][0] == u1)
    details = await select_match_details(first["match_id"])
    check("select_match_details has what the Discord message needs",
          details is not None and details["discord_id"] == "test-m1" and details["name"] == "Test Match One"
          and details["company"] == "TestCo" and details["title"] == "Test Match Intern 1"
          and details["url"] == "https://example.com/test-match-1" and approx(details["similarity_score"], 0.66))
    check("select_match_details returns None when missing", await select_match_details(999999999) is None)
    await expect("select rejects a limit of 0", ValueError, select_matches_for_user(u1, limit=0))
    await expect("select rejects a text match id", TypeError, select_match_by_id("5"))

    print("\n--- match_delete ---")
    gone = await delete_match(first["match_id"])
    check("delete_match returns the deleted row", gone is not None and gone["match_id"] == first["match_id"])
    check("the match is really gone", await select_match_by_id(first["match_id"]) is None)
    check("the user and internship are still there",
          await count("SELECT count(*) FROM users WHERE user_id = $1", u1) == 1
          and await count("SELECT count(*) FROM internships WHERE id = $1", i1) == 1)
    check("delete_match returns None when there was nothing to delete", await delete_match(first["match_id"]) is None)
    by_pair = await delete_match_by_pair(u2, i1)
    check("delete_match_by_pair returns the deleted row", by_pair is not None and by_pair["user_id"] == u2)
    check("delete_match_by_pair returns None when they weren't matched", await delete_match_by_pair(u2, i1) is None)
    await expect("delete rejects a text id", TypeError, delete_match("5"))
    async with connection.get_pool().acquire() as conn:
        await conn.execute("DELETE FROM users WHERE user_id = $1", u3)
    check("deleting a user also deletes their matches",
          await count("SELECT count(*) FROM matches WHERE user_id = $1", u3) == 0)
    async with connection.get_pool().acquire() as conn:
        await conn.execute("DELETE FROM internships WHERE id = $1", i2)
    check("deleting an internship also deletes its matches",
          await count("SELECT count(*) FROM matches WHERE internship_id = $1", i2) == 0)

    await cleanup()
    await connection.close_pool()
    print(f"\n{'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' CHECK(S) FAILED'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    asyncio.run(main())