"""Checks the resume files against a real database:
resume_queries, resume_insert, resume_update, resume_select, and resume_delete.

Run from the repo root (the folder that contains db/):
    python -m db.crud.test_resumes   (use python -m db.test_resumes if you keep this file in db/)

It creates members named "Test Resume ..." and removes them again at the end.
"""
import asyncio
import sys

import asyncpg
import numpy as np
from db.crud import Connection

from db.crud.resume_delete import delete_resume, delete_resume_by_discord_id
from db.crud.resume_insert import insert_resume, upsert_resume
from db.crud.resume_queries import RESUME_DIM, check_user_id, insert_query, resume_fields, upsert_query
from db.crud.resume_select import select_resume_by_discord_id, select_resume_by_user_id
from db.crud.resume_update import update_resume
from db.crud.user_insert import insert_user

failures = []


def vec():
    return np.random.rand(RESUME_DIM).astype(np.float32)


def same(a, b):
    return a is not None and b is not None and np.allclose(a, b)


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


async def count(sql, *args):
    async with Connection.get_pool().acquire() as conn:
        return await conn.fetchval(sql, *args)


async def cleanup():
    async with Connection.get_pool().acquire() as conn:
        await conn.execute("DELETE FROM users WHERE discord_id LIKE 'test-r%' OR name LIKE 'Test Resume %'")


def test_resume_queries():
    print("\n--- resume_queries (no database needed) ---")
    fields = resume_fields({"user_id": 5, "skills": list(range(RESUME_DIM))})
    check("resume_fields puts user_id first", [c for c, _ in fields] == ["user_id", "skills"])
    check("resume_fields turns a list into a float32 array",
          isinstance(fields[1][1], np.ndarray) and fields[1][1].dtype == np.float32)
    check("resume_fields keeps None (stores NULL)",
          resume_fields({"user_id": 5, "skills": None, "education": vec()})[1][1] is None)
    raises("rejects an unknown column", ValueError, lambda: resume_fields({"user_id": 1, "bogus": vec()}))
    raises("rejects a vector of the wrong length", ValueError, lambda: resume_fields({"user_id": 1, "skills": [1, 2, 3]}))
    raises("rejects text instead of numbers", TypeError, lambda: resume_fields({"user_id": 1, "skills": ["a"] * RESUME_DIM}))
    raises("rejects NaN", ValueError, lambda: resume_fields({"user_id": 1, "skills": [float("nan")] * RESUME_DIM}))
    raises("rejects a 2-D array", ValueError, lambda: resume_fields({"user_id": 1, "skills": np.zeros((2, RESUME_DIM))}))
    raises("rejects a missing user_id", ValueError, lambda: resume_fields({"skills": vec()}))
    raises("rejects a text user_id", TypeError, lambda: resume_fields({"user_id": "5", "skills": vec()}))
    raises("rejects True as a user_id", TypeError, lambda: check_user_id(True))
    raises("rejects a record with no vectors", ValueError, lambda: resume_fields({"user_id": 1}))
    raises("rejects a non-dict", TypeError, lambda: resume_fields([vec()]))
    raises("update fields reject user_id", ValueError,
           lambda: resume_fields({"user_id": 1, "skills": vec()}, require_user_id=False))
    check("update fields skip user_id",
          [c for c, _ in resume_fields({"skills": vec()}, require_user_id=False)] == ["skills"])
    sql, values = insert_query([("user_id", 5), ("skills", vec())])
    check("insert_query builds the INSERT",
          sql == 'INSERT INTO public.resumes ("user_id", "skills") VALUES ($1, $2) RETURNING *' and len(values) == 2)
    sql, _ = upsert_query([("user_id", 5), ("skills", vec())])
    check("upsert_query only replaces the columns given",
          'DO UPDATE SET "skills" = EXCLUDED."skills" RETURNING *' in sql and '"user_id" = EXCLUDED' not in sql)


async def main():
    test_resume_queries()

    await Connection.init_pool()
    await cleanup()

    one = (await insert_user({"discord_id": "test-r1", "name": "Test Resume One"}))["user_id"]
    two = (await insert_user({"discord_id": "test-r2", "name": "Test Resume Two"}))["user_id"]
    three = (await insert_user({"discord_id": "test-r3", "name": "Test Resume Three"}))["user_id"]
    four = (await insert_user({"discord_id": "test-r4", "name": "Test Resume Four"}))["user_id"]

    print("\n--- resume_insert: insert_resume ---")
    v = {c: vec() for c in ("resume_text", "skills", "experience", "education")}
    row = await insert_resume({"user_id": one, **v})
    check("insert_resume returns the new row", row["user_id"] == one)
    check("vectors come back as 384-number numpy arrays",
          isinstance(row["skills"], np.ndarray) and row["skills"].shape == (RESUME_DIM,))
    check("the stored vectors equal what was sent", all(same(row[c], v[c]) for c in v))
    try:
        await insert_resume({"user_id": one, **v})
        check("insert_resume rejects a second resume for the same user", False)
    except asyncpg.UniqueViolationError:
        check("insert_resume rejects a second resume for the same user", True)
    try:
        await insert_resume({"user_id": 999999999, "skills": vec()})
        check("insert_resume rejects a user that doesn't exist", False)
    except asyncpg.ForeignKeyViolationError:
        check("insert_resume rejects a user that doesn't exist", True)
    partial = await insert_resume({"user_id": two, "skills": v["skills"]})
    check("a partial insert leaves the other columns empty",
          partial["resume_text"] is None and same(partial["skills"], v["skills"]))

    print("\n--- resume_insert: upsert_resume ---")
    new_skills = vec()
    up = await upsert_resume({"user_id": one, "skills": new_skills})
    check("upsert replaces the column given", same(up["skills"], new_skills))
    check("upsert keeps the columns not given", same(up["resume_text"], v["resume_text"]))
    check("upsert did not create a second resume", await count("SELECT count(*) FROM resumes WHERE user_id = $1", one) == 1)
    rt, ed = vec(), vec()
    up2 = await upsert_resume({"user_id": two, "resume_text": rt, "education": ed})
    check("upsert fills in new columns on an existing resume",
          same(up2["resume_text"], rt) and same(up2["education"], ed) and same(up2["skills"], v["skills"]))
    created = await upsert_resume({"user_id": three, **v})
    check("upsert creates a resume when the user has none", created["user_id"] == three and same(created["skills"], v["skills"]))
    try:
        await upsert_resume({"user_id": 999999999, "skills": vec()})
        check("upsert rejects a user that doesn't exist", False)
    except asyncpg.ForeignKeyViolationError:
        check("upsert rejects a user that doesn't exist", True)
    results = await asyncio.gather(*[upsert_resume({"user_id": four, "skills": vec()}) for _ in range(10)])
    check("10 simultaneous upserts leave exactly one resume",
          len(results) == 10 and await count("SELECT count(*) FROM resumes WHERE user_id = $1", four) == 1)

    print("\n--- resume_update ---")
    new_edu = vec()
    upd = await update_resume(one, {"education": new_edu})
    check("update changes the column given", same(upd["education"], new_edu))
    check("update leaves the other columns alone",
          same(upd["skills"], new_skills) and same(upd["experience"], v["experience"]))
    check("update returns None when the user has no resume", await update_resume(999999999, {"skills": vec()}) is None)
    cleared = await update_resume(two, {"education": None})
    check("update can set a column back to empty", cleared["education"] is None)
    for label, exc, args in [
        ("update rejects an empty update", ValueError, (one, {})),
        ("update rejects user_id inside the changes", ValueError, (one, {"user_id": 2, "skills": vec()})),
        ("update rejects an unknown column", ValueError, (one, {"bogus": vec()})),
        ("update rejects a vector of the wrong length", ValueError, (one, {"skills": [1.0]})),
        ("update rejects a text user_id", TypeError, (str(one), {"skills": vec()})),
    ]:
        try:
            await update_resume(*args)
            check(label, False)
        except exc:
            check(label, True)

    print("\n--- resume_select ---")
    got = await select_resume_by_user_id(one)
    check("select by user_id", got is not None and got["user_id"] == one and same(got["education"], new_edu))
    check("select by user_id returns None when missing", await select_resume_by_user_id(999999999) is None)
    by_discord = await select_resume_by_discord_id("test-r1")
    check("select by discord id finds the same resume", by_discord is not None and by_discord["user_id"] == one)
    check("select by discord id returns None for an unknown id", await select_resume_by_discord_id("test-nobody") is None)
    no_resume = (await insert_user({"discord_id": "test-r5", "name": "Test Resume Five"}))["user_id"]
    check("select returns None for a member with no resume", await select_resume_by_discord_id("test-r5") is None)
    try:
        await select_resume_by_discord_id(123)
        check("select rejects a non-string discord id", False)
    except TypeError:
        check("select rejects a non-string discord id", True)

    print("\n--- resume_delete ---")
    gone = await delete_resume(one)
    check("delete returns the deleted row", gone is not None and gone["user_id"] == one)
    check("the resume is really gone", await select_resume_by_user_id(one) is None)
    check("the member is still there", await count("SELECT count(*) FROM users WHERE user_id = $1", one) == 1)
    check("delete returns None when there was nothing to delete", await delete_resume(one) is None)
    by_disc = await delete_resume_by_discord_id("test-r2")
    check("delete by discord id returns the deleted row", by_disc is not None and by_disc["user_id"] == two)
    check("delete by discord id returns None when nothing matches", await delete_resume_by_discord_id("test-nobody") is None)
    async with Connection.get_pool().acquire() as conn:
        await conn.execute("DELETE FROM users WHERE user_id = $1", three)
    check("deleting a user also deletes their resume", await select_resume_by_user_id(three) is None)

    await cleanup()
    await Connection.close_pool()
    print(f"\n{'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' CHECK(S) FAILED'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    asyncio.run(main())