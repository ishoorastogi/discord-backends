"""Checks the finance files against a real database:
finance_queries, finance_insert, finance_update, finance_select, and finance_delete.

Run from the repo root (the folder that contains db/):
    python -m db.crud.test_finance

It creates members named "Test Finance ..." and finance records for them, and removes
them all at the end (even if a check crashes).

To also test the finance_user role, set FINANCE_USER_PASSWORD in your environment or
.env. To check that another role is blocked, also set BROTHERHOOD_BOT_PASSWORD.
"""
import asyncio
import os
import sys
from decimal import Decimal

import asyncpg

from db.crud import Connection as connection
from db.crud.finance_delete import delete_finance
from db.crud.finance_insert import insert_finance, insert_finances
from db.crud.finance_queries import (
    check_amount,
    check_finance_id,
    check_type,
    finance_fields,
    insert_query,
    select_query,
    totals_query,
)
from db.crud.finance_select import select_finance_by_id, select_finance_totals, select_finances
from db.crud.finance_update import update_finance
from db.crud.user_insert import insert_user

failures = []
created_ids = []


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


def track(row):
    created_ids.append(row["finance_id"])
    return row


async def count(sql, *args):
    async with connection.get_pool().acquire() as conn:
        return await conn.fetchval(sql, *args)


async def cleanup():
    async with connection.get_pool().acquire() as conn:
        # finances first: deleting a user would only detach its records (user_id -> NULL)
        await conn.execute(
            "DELETE FROM finances WHERE finance_id = ANY($1::int[]) OR user_id IN "
            "(SELECT user_id FROM users WHERE discord_id LIKE 'test-f%' OR name LIKE 'Test Finance %')",
            created_ids,
        )
        await conn.execute("DELETE FROM users WHERE discord_id LIKE 'test-f%' OR name LIKE 'Test Finance %'")


def test_finance_queries():
    print("\n--- finance_queries (no database needed) ---")
    check("check_amount accepts a Decimal", check_amount(Decimal("12.5")) == Decimal("12.50"))
    check("check_amount accepts text", check_amount(" 12.50 ") == Decimal("12.50"))
    check("check_amount accepts a whole number", check_amount(5) == Decimal("5.00"))
    check("check_amount accepts a float with 2 decimals", check_amount(12.5) == Decimal("12.50"))
    check("check_amount accepts the largest amount", check_amount("99999999.99") == Decimal("99999999.99"))
    check("check_amount always returns 2 decimal places", str(check_amount("7")) == "7.00")
    raises("rejects 0", ValueError, lambda: check_amount(0))
    raises("rejects a negative amount", ValueError, lambda: check_amount("-5"))
    raises("rejects 3 decimal places", ValueError, lambda: check_amount("12.345"))
    raises("rejects a float sum like 0.1 + 0.2", ValueError, lambda: check_amount(0.1 + 0.2))
    raises("rejects NaN", ValueError, lambda: check_amount(float("nan")))
    raises("rejects infinity", ValueError, lambda: check_amount(float("inf")))
    raises("rejects an amount that's too big", ValueError, lambda: check_amount("100000000"))
    raises("rejects text that isn't a number", ValueError, lambda: check_amount("abc"))
    raises("rejects True as an amount", TypeError, lambda: check_amount(True))
    raises("rejects None as an amount", TypeError, lambda: check_amount(None))
    check("check_type cleans up capitals and spaces", check_type(" Dues ") == "dues")
    raises("rejects an unknown type", ValueError, lambda: check_type("gift"))
    raises("rejects a type that isn't text", TypeError, lambda: check_type(5))
    raises("rejects True as an id", TypeError, lambda: check_finance_id(True))
    raises("rejects a text id", TypeError, lambda: check_finance_id("5"))

    check("finance_fields keeps the columns in order",
          finance_fields({"amount": 5, "type": "Income", "user_id": 3})
          == [("user_id", 3), ("type", "income"), ("amount", Decimal("5.00"))])
    check("user_id is optional on insert", finance_fields({"type": "expense", "amount": 5}) == [("type", "expense"), ("amount", Decimal("5.00"))])
    check("user_id can be None", finance_fields({"user_id": None, "type": "expense", "amount": 5})[0] == ("user_id", None))
    raises("rejects an unknown column", ValueError, lambda: finance_fields({"type": "dues", "amount": 5, "bogus": 1}))
    raises("rejects finance_id (it is generated)", ValueError, lambda: finance_fields({"finance_id": 1, "type": "dues", "amount": 5}))
    raises("rejects a missing type", ValueError, lambda: finance_fields({"amount": 5}))
    raises("rejects a missing amount", ValueError, lambda: finance_fields({"type": "dues"}))
    raises("rejects a text user_id", TypeError, lambda: finance_fields({"user_id": "3", "type": "dues", "amount": 5}))
    raises("rejects a non-dict", TypeError, lambda: finance_fields(["dues", 5]))
    raises("rejects an empty update", ValueError, lambda: finance_fields({}, for_insert=False))
    check("update fields accept one column", finance_fields({"amount": "9.99"}, for_insert=False) == [("amount", Decimal("9.99"))])
    raises("update fields still validate the amount", ValueError, lambda: finance_fields({"amount": -1}, for_insert=False))

    sql, values = insert_query([("type", "dues"), ("amount", Decimal("5.00"))])
    check("insert_query builds the INSERT",
          sql == 'INSERT INTO public.finances ("type", "amount") VALUES ($1, $2) RETURNING *' and values == ["dues", Decimal("5.00")])
    sql, values = select_query({"user_id": 4, "type": "Dues"}, 5)
    check("select_query numbers the placeholders and cleans the type",
          values == [4, "dues", 5] and '"user_id" = $1 AND "type" = $2' in sql and sql.endswith("ORDER BY finance_id DESC LIMIT $3"))
    check("select_query with no filters has no WHERE", "WHERE" not in select_query()[0])
    raises("select_query rejects an unknown filter", ValueError, lambda: select_query({"amount": 5}))
    raises("select_query rejects a limit of 0", ValueError, lambda: select_query(limit=0))
    raises("select_query rejects True as a limit", ValueError, lambda: select_query(limit=True))
    check("totals_query for everyone has no WHERE", "WHERE" not in totals_query()[0])
    check("totals_query for one member filters by user_id", totals_query(7)[1] == [7] and "WHERE" in totals_query(7)[0])
    raises("totals_query rejects a text user_id", TypeError, lambda: totals_query("7"))


async def run_checks():
    u1 = (await insert_user({"discord_id": "test-f1", "name": "Test Finance One"}))["user_id"]
    u2 = (await insert_user({"discord_id": "test-f2", "name": "Test Finance Two"}))["user_id"]
    u3 = (await insert_user({"discord_id": "test-f3", "name": "Test Finance Three"}))["user_id"]

    print("\n--- finance_insert: insert_finance ---")
    row = track(await insert_finance({"user_id": u1, "type": "dues", "amount": "150.00"}))
    check("insert_finance returns the new row with an id", isinstance(row["finance_id"], int) and row["user_id"] == u1)
    check("the amount comes back as an exact Decimal", row["amount"] == Decimal("150.00") and isinstance(row["amount"], Decimal))
    cents = track(await insert_finance({"user_id": u1, "type": "income", "amount": "0.10"}))
    check("small amounts are stored exactly", cents["amount"] == Decimal("0.10"))
    shouted = track(await insert_finance({"type": " EXPENSE ", "amount": 20}))
    check("type is cleaned up, and user_id can be left out", shouted["type"] == "expense" and shouted["user_id"] is None)
    await expect("insert rejects a user that doesn't exist", asyncpg.ForeignKeyViolationError,
                 insert_finance({"user_id": 999999999, "type": "dues", "amount": 5}))
    await expect("insert rejects an unknown type", ValueError, insert_finance({"type": "gift", "amount": 5}))
    await expect("insert rejects a negative amount", ValueError, insert_finance({"type": "dues", "amount": -5}))
    await expect("insert rejects 3 decimal places", ValueError, insert_finance({"type": "dues", "amount": "1.005"}))
    await expect("insert requires an amount", ValueError, insert_finance({"type": "dues"}))
    await expect("insert rejects a text user_id", TypeError, insert_finance({"user_id": str(u1), "type": "dues", "amount": 5}))
    await expect("insert rejects an unknown column", ValueError, insert_finance({"type": "dues", "amount": 5, "bogus": 1}))
    try:
        async with connection.get_pool().acquire() as conn:
            await conn.execute("INSERT INTO finances (type, amount) VALUES ('dues', -5)")
        check("the database itself also rejects a negative amount", False)
    except asyncpg.CheckViolationError:
        check("the database itself also rejects a negative amount", True)

    print("\n--- finance_insert: insert_finances ---")
    batch = await insert_finances([
        {"user_id": u2, "type": "dues", "amount": "25.50"},
        {"user_id": u2, "type": "income", "amount": "100"},
        {"user_id": u2, "type": "expense", "amount": "10"},
    ])
    for item in batch:
        track(item)
    check("insert_finances adds every row", len(batch) == 3 and len({r["finance_id"] for r in batch}) == 3)
    await expect("insert_finances saves nothing if one row fails", asyncpg.ForeignKeyViolationError,
                 insert_finances([
                     {"user_id": u3, "type": "dues", "amount": "77.77"},
                     {"user_id": 999999999, "type": "dues", "amount": "77.77"},
                 ]))
    check("...so the good row wasn't saved either",
          await count("SELECT count(*) FROM finances WHERE user_id = $1", u3) == 0)
    await expect("insert_finances rejects a non-list", TypeError, insert_finances({"type": "dues", "amount": 5}))
    check("insert_finances accepts an empty list", await insert_finances([]) == [])

    print("\n--- finance_update ---")
    upd = await update_finance(row["finance_id"], {"amount": "175.00"})
    assert upd is not None
    check("update changes the amount", upd["amount"] == Decimal("175.00"))
    check("update leaves the other columns alone", upd["type"] == "dues" and upd["user_id"] == u1)
    upd2 = await update_finance(row["finance_id"], {"type": "Income"})
    assert upd2 is not None
    check("update can correct the type", upd2["type"] == "income")
    upd3 = await update_finance(row["finance_id"], {"user_id": u3})
    assert upd3 is not None
    check("update can move a record to another member", upd3["user_id"] == u3)
    upd4 = await update_finance(row["finance_id"], {"user_id": None})
    assert upd4 is not None
    check("update can detach a record from its member", upd4["user_id"] is None)
    check("update returns None when the id doesn't exist", await update_finance(999999999, {"amount": 5}) is None)
    await expect("update rejects an empty update", ValueError, update_finance(row["finance_id"], {}))
    await expect("update can't change the id", ValueError, update_finance(row["finance_id"], {"finance_id": 5}))
    await expect("update rejects a bad amount", ValueError, update_finance(row["finance_id"], {"amount": 0}))
    await expect("update rejects a bad type", ValueError, update_finance(row["finance_id"], {"type": "gift"}))
    await expect("update rejects a user that doesn't exist", asyncpg.ForeignKeyViolationError,
                 update_finance(row["finance_id"], {"user_id": 999999999}))
    await expect("update rejects a text id", TypeError, update_finance(str(row["finance_id"]), {"amount": 5}))

    print("\n--- finance_select ---")
    got = await select_finance_by_id(cents["finance_id"])
    check("select by id", got is not None and got["amount"] == Decimal("0.10"))
    check("select by id returns None when missing", await select_finance_by_id(999999999) is None)
    mine = await select_finances({"user_id": u2})
    check("filter by member returns only their records", len(mine) == 3 and all(r["user_id"] == u2 for r in mine))
    check("results come back newest first", [r["finance_id"] for r in mine] == sorted((r["finance_id"] for r in mine), reverse=True))
    only_dues = await select_finances({"user_id": u2, "type": "DUES"})
    check("filters combine and ignore capitals", len(only_dues) == 1 and only_dues[0]["amount"] == Decimal("25.50"))
    check("a member with no records gets []", await select_finances({"user_id": u3}) == [])
    check("limit caps the number of rows", len(await select_finances({"user_id": u2}, limit=2)) == 2)
    check("no filters returns a list", isinstance(await select_finances(limit=5), list))
    await expect("select rejects an unknown filter", ValueError, select_finances({"amount": 5}))
    await expect("select rejects a limit of 0", ValueError, select_finances(limit=0))
    totals = await select_finance_totals(u2)
    check("totals add up each type for one member",
          totals == {"income": Decimal("100.00"), "expense": Decimal("10.00"), "dues": Decimal("25.50")})
    check("a member with no records gets zeros",
          await select_finance_totals(u3) == {"income": Decimal("0.00"), "expense": Decimal("0.00"), "dues": Decimal("0.00")})
    everyone = await select_finance_totals()
    check("totals for everyone include this member's records",
          everyone["income"] >= Decimal("100.00") and everyone["dues"] >= Decimal("25.50"))
    await expect("totals reject a text user_id", TypeError, select_finance_totals("2"))

    print("\n--- finance_delete ---")
    gone = await delete_finance(row["finance_id"])
    check("delete returns the deleted row", gone is not None and gone["finance_id"] == row["finance_id"])
    check("the record is really gone", await select_finance_by_id(row["finance_id"]) is None)
    check("delete returns None when there was nothing to delete", await delete_finance(row["finance_id"]) is None)
    await expect("delete rejects a text id", TypeError, delete_finance("5"))
    async with connection.get_pool().acquire() as conn:
        await conn.execute("DELETE FROM users WHERE user_id = $1", u2)
    check("deleting a member keeps their records but detaches them",
          await count("SELECT count(*) FROM finances WHERE finance_id = ANY($1::int[]) AND user_id IS NULL",
                      [r["finance_id"] for r in batch]) == 3)

    fin_pw = os.getenv("FINANCE_USER_PASSWORD")
    bot_pw = os.getenv("BROTHERHOOD_BOT_PASSWORD")
    if fin_pw:
        print("\n--- database roles ---")
        try:
            role_row = track(await insert_finance({"user_id": u1, "type": "dues", "amount": "30"}, "finance_user", fin_pw))
        except (asyncpg.InvalidPasswordError, asyncpg.InvalidAuthorizationSpecificationError):
            print("SKIP  couldn't log in as finance_user (is the role created with that password?)")
        else:
            check("finance_user can insert finances", role_row["finance_id"] is not None)
            check("finance_user can select finances",
                  (await select_finance_by_id(role_row["finance_id"], "finance_user", fin_pw)) is not None)
            changed = await update_finance(role_row["finance_id"], {"amount": "31"}, "finance_user", fin_pw)
            check("finance_user can update finances", changed is not None and changed["amount"] == Decimal("31.00"))
            check("finance_user can read totals",
                  (await select_finance_totals(u1, "finance_user", fin_pw))["dues"] >= Decimal("31.00"))
            check("finance_user can delete finances",
                  (await delete_finance(role_row["finance_id"], "finance_user", fin_pw)) is not None)
            if bot_pw:
                try:
                    await select_finances(limit=1, username="brotherhood_bot", password=bot_pw)
                    check("brotherhood_bot is blocked from finances", False)
                except asyncpg.InsufficientPrivilegeError:
                    check("brotherhood_bot is blocked from finances", True)
                except (asyncpg.InvalidPasswordError, asyncpg.InvalidAuthorizationSpecificationError):
                    print("SKIP  couldn't log in as brotherhood_bot")
    else:
        print("\n(skipping role tests: set FINANCE_USER_PASSWORD, and BROTHERHOOD_BOT_PASSWORD, to run them)")


async def main():
    test_finance_queries()

    await connection.init_pool()
    try:
        await cleanup()
        await run_checks()
    finally:
        await cleanup()
        await connection.close_pool()
    print(f"\n{'ALL CHECKS PASSED' if not failures else str(len(failures)) + ' CHECK(S) FAILED'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    asyncio.run(main())