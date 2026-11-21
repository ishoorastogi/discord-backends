"""Checks the internship files against a real database:
internship_queries, internship_insert, internship_update, internship_select,
and internship_delete.

Run from the repo root (the folder that contains db/):
    python -m db.crud.test_internship

It creates internships with urls starting https://example.com/test-internship and a
member named "Test Internship User", and removes them again at the end.
"""
import asyncio
import sys

import asyncpg
import numpy as np

from db.crud import Connection as connection
from db.crud.internship_delete import delete_internship, delete_internship_by_url
from db.crud.internship_insert import (
    insert_internship,
    insert_internships,
    upsert_internship,
    upsert_internships,
)
from db.crud.internship_queries import (
    EMBEDDING_DIM,
    check_internship_id,
    insert_query,
    internship_fields,
    select_query,
    upsert_query,
)
from db.crud.internship_select import (
    select_internship_by_id,
    select_internship_by_url,
    select_internships,
)
from db.crud.internship_update import update_internship
from db.crud.user_insert import insert_user

URL = "https://example.com/test-internship"
failures = []


def vec():
    return np.random.rand(EMBEDDING_DIM).astype(np.float32)


def same(a, b):
    return a is not None and b is not None and np.allclose(a, b)


def make(n, **extra):
    return {"company": "TestCo", "title": f"Test Intern {n}", "url": f"{URL}-{n}", **extra}


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
        await conn.execute("DELETE FROM internships WHERE url LIKE 'https://example.com/test-internship%'")
        await conn.execute("DELETE FROM users WHERE discord_id LIKE 'test-i%'")


def test_internship_queries():
    print("\n--- internship_queries (no database needed) ---")
    fields = internship_fields({"company": " Acme ", "title": "Intern", "location": "   ", "embedding": list(range(EMBEDDING_DIM))})
    check("internship_fields trims text", fields[0] == ("company", "Acme"))
    check("blank optional text becomes None", ("location", None) in fields)
    check("embedding becomes a float32 array",
          isinstance(fields[-1][1], np.ndarray) and fields[-1][1].dtype == np.float32)
    raises("rejects an unknown column", ValueError, lambda: internship_fields({"company": "A", "title": "B", "bogus": 1}))
    raises("rejects the id column", ValueError, lambda: internship_fields({"id": 3, "company": "A", "title": "B"}))
    raises("rejects a missing company", ValueError, lambda: internship_fields({"title": "B"}))
    raises("rejects a missing title", ValueError, lambda: internship_fields({"company": "A"}))
    raises("rejects a blank title", ValueError, lambda: internship_fields({"company": "A", "title": "   "}))
    raises("rejects text that isn't text", TypeError, lambda: internship_fields({"company": 5, "title": "B"}))
    raises("rejects an embedding of the wrong length", ValueError,
           lambda: internship_fields({"company": "A", "title": "B", "embedding": [1.0]}))
    raises("rejects a non-dict", TypeError, lambda: internship_fields(["A"]))
    raises("update fields reject an empty record", ValueError, lambda: internship_fields({}, for_insert=False))
    check("update fields don't require company or title",
          internship_fields({"location": "Austin"}, for_insert=False) == [("location", "Austin")])
    raises("update fields still reject a blank title", ValueError,
           lambda: internship_fields({"title": ""}, for_insert=False))
    raises("upsert requires a url", ValueError,
           lambda: internship_fields({"company": "A", "title": "B"}, require_url=True))
    raises("upsert rejects a blank url", ValueError,
           lambda: internship_fields({"company": "A", "title": "B", "url": "  "}, require_url=True))
    raises("rejects True as an id", TypeError, lambda: check_internship_id(True))
    raises("rejects a text id", TypeError, lambda: check_internship_id("5"))
    sql, values = insert_query([("company", "A"), ("title", "B")])
    check("insert_query builds the INSERT",
          sql == 'INSERT INTO public.internships ("company", "title") VALUES ($1, $2) RETURNING *' and values == ["A", "B"])
    sql, _ = upsert_query([("company", "A"), ("title", "B"), ("url", "u")])
    check("upsert_query replaces the given columns but never rewrites url",
          'DO UPDATE SET "company" = EXCLUDED."company", "title" = EXCLUDED."title" RETURNING *' in sql)
    sql, values = select_query({"company": " TestCo ", "role_type": "Intern"}, 5)
    check("select_query lowercases filters and numbers the placeholders",
          values == ["testco", "intern", 5] and 'lower("company") = $1 AND lower("role_type") = $2' in sql and sql.endswith("LIMIT $3"))
    check("select_query with no filters has no WHERE", "WHERE" not in select_query()[0])
    raises("select_query rejects an unknown filter", ValueError, lambda: select_query({"url": "x"}))
    raises("select_query rejects a limit of 0", ValueError, lambda: select_query(limit=0))
    raises("select_query rejects a limit that's too big", ValueError, lambda: select_query(limit=5000))
    raises("select_query rejects True as a limit", ValueError, lambda: select_query(limit=True))
    raises("select_query rejects a non-text filter value", TypeError, lambda: select_query({"company": 5}))


async def main():
    test_internship_queries()

    await connection.init_pool()
    await cleanup()

    print("\n--- internship_insert: insert_internship ---")
    emb = vec()
    row = await insert_internship(make(1, description="d", location="Dallas", role_type="intern",
                                       requirements="python", embedding=emb))
    check("insert_internship returns the new row with an id", isinstance(row["id"], int) and row["company"] == "TestCo")
    check("the embedding comes back as a 384-number numpy array",
          isinstance(row["embedding"], np.ndarray) and row["embedding"].shape == (EMBEDDING_DIM,))
    check("the stored embedding equals what was sent", same(row["embedding"], emb))
    await expect("insert rejects a url that's already stored", asyncpg.UniqueViolationError, insert_internship(make(1)))
    await expect("insert requires a company", ValueError, insert_internship({"title": "Only a title"}))
    await expect("insert rejects a blank title", ValueError, insert_internship({"company": "A", "title": " "}))
    await expect("insert rejects an unknown column", ValueError, insert_internship({**make(90), "bogus": 1}))
    partial = await insert_internship(make(2))
    check("a minimal insert leaves the other columns empty",
          partial["description"] is None and partial["embedding"] is None)
    blank = await insert_internship(make(3, description="   "))
    check("blank optional text is stored as NULL", blank["description"] is None)

    print("\n--- internship_insert: batches ---")
    rows = await insert_internships([make(4), make(5)])
    check("insert_internships adds every row", len(rows) == 2 and rows[0]["id"] != rows[1]["id"])
    await expect("insert_internships saves nothing if one row fails", asyncpg.UniqueViolationError,
                 insert_internships([make(6), make(4)]))
    check("...so the good row wasn't saved either",
          await count("SELECT count(*) FROM internships WHERE url = $1", f"{URL}-6") == 0)
    await expect("insert_internships rejects a non-list", TypeError, insert_internships(make(7)))
    check("insert_internships accepts an empty list", await insert_internships([]) == [])

    print("\n--- internship_insert: upsert_internship ---")
    up = await upsert_internship({**make(1), "title": "Test Intern 1 Updated"})
    check("upsert updates the row with the same url", up["id"] == row["id"])
    check("upsert changed the title", up["title"] == "Test Intern 1 Updated")
    check("upsert kept the columns not given", up["description"] == "d" and same(up["embedding"], emb))
    check("upsert did not create a second row",
          await count("SELECT count(*) FROM internships WHERE url = $1", f"{URL}-1") == 1)
    new = await upsert_internship(make(8, location="Austin"))
    check("upsert creates a row when the url is new", new["id"] != row["id"] and new["location"] == "Austin")
    await expect("upsert requires a url", ValueError, upsert_internship({"company": "A", "title": "B"}))
    await expect("upsert requires a title", ValueError, upsert_internship({"company": "A", "url": f"{URL}-91"}))
    results = await asyncio.gather(*[upsert_internship(make(9, location=f"City {i}")) for i in range(10)])
    check("10 simultaneous upserts leave exactly one row",
          len(results) == 10 and await count("SELECT count(*) FROM internships WHERE url = $1", f"{URL}-9") == 1)
    batch = await upsert_internships([make(10), {**make(10), "title": "Test Intern 10b"}])
    check("upsert_internships handles repeats inside one batch",
          len(batch) == 2 and batch[0]["id"] == batch[1]["id"]
          and await count("SELECT title FROM internships WHERE url = $1", f"{URL}-10") == "Test Intern 10b")
    await expect("upsert_internships saves nothing if one row is invalid", ValueError,
                 upsert_internships([make(11), {"company": "A", "title": "B"}]))
    check("...so the valid row wasn't saved",
          await count("SELECT count(*) FROM internships WHERE url = $1", f"{URL}-11") == 0)

    print("\n--- internship_update ---")
    upd = await update_internship(row["id"], {"location": "Houston"})
    assert upd is not None
    check("update changes the column given", upd["location"] == "Houston")
    check("update leaves the other columns alone",
          upd["company"] == "TestCo" and upd["description"] == "d" and same(upd["embedding"], emb))
    new_emb = vec()
    upd2 = await update_internship(row["id"], {"embedding": new_emb})
    assert upd2 is not None
    check("update can replace the embedding", same(upd2["embedding"], new_emb))
    upd3 = await update_internship(row["id"], {"description": None})
    assert upd3 is not None
    check("update can set a column back to empty", upd3["description"] is None)
    check("update returns None when the id doesn't exist", await update_internship(999999999, {"title": "x"}) is None)
    await expect("update rejects an empty update", ValueError, update_internship(row["id"], {}))
    await expect("update can't change the id", ValueError, update_internship(row["id"], {"id": 5}))
    await expect("update rejects a blank title", ValueError, update_internship(row["id"], {"title": ""}))
    await expect("update rejects an unknown column", ValueError, update_internship(row["id"], {"bogus": 1}))
    await expect("update rejects a text id", TypeError, update_internship(str(row["id"]), {"title": "x"}))
    await expect("update rejects a url already used by another internship", asyncpg.UniqueViolationError,
                 update_internship(partial["id"], {"url": make(1)["url"]}))

    print("\n--- internship_select ---")
    got = await select_internship_by_id(row["id"])
    check("select by id", got is not None and got["url"] == f"{URL}-1")
    check("select by id returns None when missing", await select_internship_by_id(999999999) is None)
    check("select by url", (await select_internship_by_url(f"  {URL}-1 ") or {}).get("id") == row["id"])
    check("select by url returns None for an unknown url (a new listing)",
          await select_internship_by_url(f"{URL}-nope") is None)
    await expect("select by url rejects a blank url", ValueError, select_internship_by_url("  "))
    everyone = await select_internships({"company": "testco"}, limit=1000)
    ids = [r["id"] for r in everyone]
    check("filter by company ignores case", row["id"] in ids and partial["id"] in ids)
    check("results come back in id order", ids == sorted(ids))
    austin = await select_internships({"company": "TestCo", "location": "AUSTIN"})
    check("filters combine with AND", [r["id"] for r in austin] == [new["id"]])
    check("filtering on a value nobody has returns []", await select_internships({"role_type": "zzz-none"}) == [])
    check("limit caps the number of rows", len(await select_internships({"company": "TestCo"}, limit=2)) == 2)
    check("no filters returns a list", isinstance(await select_internships(), list))
    await expect("select rejects an unknown filter", ValueError, select_internships({"url": "x"}))
    await expect("select rejects a limit of 0", ValueError, select_internships(limit=0))

    print("\n--- internship_delete ---")
    user = await insert_user({"discord_id": "test-i1", "name": "Test Internship User"})
    async with connection.get_pool().acquire() as conn:
        await conn.execute(
            "INSERT INTO matches (user_id, internship_id, similarity_score) VALUES ($1, $2, 0.9)",
            user["user_id"], row["id"])
    check("a match exists before the delete",
          await count("SELECT count(*) FROM matches WHERE internship_id = $1", row["id"]) == 1)
    gone = await delete_internship(row["id"])
    check("delete returns the deleted row", gone is not None and gone["id"] == row["id"])
    check("the internship is really gone", await select_internship_by_id(row["id"]) is None)
    check("deleting an internship also deletes its matches",
          await count("SELECT count(*) FROM matches WHERE internship_id = $1", row["id"]) == 0)
    check("the member is still there", await count("SELECT count(*) FROM users WHERE user_id = $1", user["user_id"]) == 1)
    check("delete returns None when there was nothing to delete", await delete_internship(row["id"]) is None)
    by_url = await delete_internship_by_url(f"{URL}-2")
    check("delete by url returns the deleted row", by_url is not None and by_url["id"] == partial["id"])
    check("delete by url returns None when nothing matches", await delete_internship_by_url(f"{URL}-nope") is None)
    await expect("delete by url rejects a blank url", ValueError, delete_internship_by_url(""))
    await expect("delete rejects a text id", TypeError, delete_internship("5"))

    await cleanup()
    await connection.close_pool()
    print(f"\n{'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' CHECK(S) FAILED'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    asyncio.run(main())