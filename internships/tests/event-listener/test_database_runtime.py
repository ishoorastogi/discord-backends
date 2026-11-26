import asyncio
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from unittest.mock import AsyncMock, Mock

import pytest


runtime_module = import_module("shared.db-utils.runtime")
Connection = import_module("shared.db-utils.crud.Connection")
query_rows = import_module("shared.db-utils.crud.query").query_rows


async def current_loop():
    return asyncio.get_running_loop()


@pytest.fixture
def runtime(monkeypatch):
    monkeypatch.setattr(Connection, "_pool", None)
    monkeypatch.setattr(Connection, "_pool_init_lock", None)
    monkeypatch.setattr(Connection, "_role_pools", {})
    db_runtime = runtime_module.DatabaseRuntime()
    yield db_runtime
    db_runtime.close()


def test_start_creates_one_loop_without_opening_connections(runtime, monkeypatch):
    create_pool = AsyncMock()
    monkeypatch.setattr(Connection.asyncpg, "create_pool", create_pool)

    with pytest.raises(RuntimeError, match="has not been started"):
        runtime.run(current_loop())

    runtime.start()
    loop = runtime.run(current_loop())
    runtime.start()
    assert runtime.run(current_loop()) is loop
    create_pool.assert_not_called()


def test_run_returns_result_and_propagates_exception(runtime):
    error = ConnectionError("database unavailable")

    async def operation(fail=False):
        await asyncio.sleep(0)
        if fail:
            raise error
        return 42

    runtime.start()
    with pytest.raises(ConnectionError) as raised:
        runtime.run(operation(fail=True))
    assert raised.value is error
    assert runtime.run(operation()) == 42


def test_runtime_rejects_calls_from_other_threads(runtime):
    runtime.start()
    loop = runtime.run(current_loop())

    with ThreadPoolExecutor(max_workers=1) as executor:
        for method, args in (
            (runtime.start, ()),
            (runtime.run, (current_loop(),)),
            (runtime.close, ()),
        ):
            future = executor.submit(method, *args)
            with pytest.raises(RuntimeError, match="owning thread"):
                future.result(timeout=3)

    assert runtime.run(current_loop()) is loop


def test_default_and_role_queries_reuse_pools_and_close_them_on_the_loop(runtime, monkeypatch):
    closed_loops = []

    async def close_pool():
        closed_loops.append(asyncio.get_running_loop())

    default_pool = Mock(close=AsyncMock(side_effect=close_pool))
    role_pool = Mock(close=AsyncMock(side_effect=close_pool))
    for pool in (default_pool, role_pool):
        acquire = pool.acquire.return_value = AsyncMock()
        acquire.__aenter__.return_value.fetch = AsyncMock(return_value=[{"value": 42}])
    pools = iter([default_pool, role_pool])

    async def open_pool(**settings):
        await asyncio.sleep(0)
        return next(pools)

    async def query_default_twice():
        return await asyncio.gather(query_rows("SELECT 42 AS value"), query_rows("SELECT 42 AS value"))

    create_pool = AsyncMock(side_effect=open_pool)
    monkeypatch.setattr(Connection.asyncpg, "create_pool", create_pool)

    runtime.start()
    loop = runtime.run(current_loop())
    create_pool.assert_not_called()
    assert runtime.run(query_default_twice()) == [[{"value": 42}], [{"value": 42}]]
    assert runtime.run(query_rows("SELECT 42 AS value", username="writer", password="test")) == [{"value": 42}]
    assert create_pool.await_count == 2
    assert default_pool.acquire.call_count == 2
    assert role_pool.acquire.call_count == 1

    runtime.close()
    runtime.close()
    assert closed_loops == [loop, loop]
    assert loop.is_closed()
    assert Connection._pool is None
    assert Connection._role_pools == {}


def test_close_failure_still_closes_loop_and_rejects_execution(runtime, monkeypatch):
    close_pool = AsyncMock(side_effect=ConnectionError("pool shutdown failed"))
    monkeypatch.setattr(Connection, "_role_pools", {"writer": Mock(close=close_pool)})
    default_pool = Mock(close=AsyncMock())
    monkeypatch.setattr(Connection, "_pool", default_pool)

    runtime.start()
    loop = runtime.run(current_loop())
    with pytest.raises(ConnectionError, match="pool shutdown failed"):
        runtime.close()

    runtime.close()
    close_pool.assert_awaited_once()
    default_pool.close.assert_awaited_once()
    assert loop.is_closed()
    assert Connection._pool is None
    assert Connection._role_pools == {}
    with pytest.raises(RuntimeError, match="closed"):
        runtime.run(current_loop())
    with pytest.raises(RuntimeError, match="closed"):
        runtime.start()


def test_close_before_start_is_safe_and_final(runtime):
    runtime.close()
    runtime.close()
    with pytest.raises(RuntimeError, match="closed"):
        runtime.start()
