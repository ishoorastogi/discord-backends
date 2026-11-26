from dataclasses import fields
from importlib import import_module
import os
import re
from unittest.mock import Mock
from uuid import uuid4

import numpy as np
import pytest

from internships.src import main
from models import Resume


writer = import_module("writer-handler")
crud = import_module("shared.db-utils.crud.resume_queries")
Connection = import_module("shared.db-utils.crud.Connection")
query_rows = import_module("shared.db-utils.crud.query").query_rows
DatabaseRuntime = import_module("shared.db-utils.runtime").DatabaseRuntime
SCHEMA = main.SERVICE_DIR.parent / "db" / "schema.sql"


def test_vector_fields_match_model_crud_and_schema():
    schema = SCHEMA.read_text().split("CREATE TABLE resumes (", 1)[1].split("\n);", 1)[0]
    column_types = re.findall(r"^\s*(\w+)\s+vector\((\d+)\)", schema, re.I | re.M)
    model_columns = [field.name for field in fields(Resume) if field.name.endswith("_vector")]
    assert model_columns == crud.VECTOR_COLUMNS == [column for column, _ in column_types]
    assert len(model_columns) == 6
    assert {int(dimension) for _, dimension in column_types} == {crud.RESUME_DIM} == {384}
    assert re.search(r"user_id\s+BIGINT PRIMARY KEY\s+REFERENCES users\(user_id\)\s+ON DELETE CASCADE", schema)


def event_for(discord_id, name):
    vectors = {
        column: vector.tolist()
        for column, vector in zip(crud.VECTOR_COLUMNS, np.eye(6, crud.RESUME_DIM))
    }
    return {"event": "RESUME_WRITE", "request_id": "request-test", "data": {
        "discord_id": discord_id,
        "name": "Envelope name",
        "resume": Resume("private resume", name=name, **vectors),
        "normalized_resume": {},
    }}


MISSING = object()


@pytest.mark.parametrize(("field", "value", "warning"), [
    ("skills_vector", MISSING, "Incomplete resume embeddings"),
    ("overall_vector", None, "Incomplete resume embeddings"),
    ("overall_vector", [0.5], "Invalid resume embeddings"),
    ("skills_vector", [float("nan")] * 384, "Invalid resume embeddings"),
])
def test_writer_rejects_incomplete_or_invalid_vectors(monkeypatch, field, value, warning):
    event = event_for("123", "Candidate")
    resume = event["data"]["resume"]
    if value is MISSING:
        delattr(resume, field)
    else:
        setattr(resume, field, value)
    runtime = Mock()
    logger = Mock()
    monkeypatch.setattr(writer, "logger", logger)

    assert writer.handle_resume_write(event, db_runtime=runtime) is None
    runtime.run.assert_not_called()
    logger.warning.assert_called_once()
    assert warning in logger.warning.call_args.args[0]


@pytest.fixture
def pg_runtime(monkeypatch):
    port = os.environ.get("RESUME_WRITER_TEST_PORT")
    if port is None:
        pytest.skip("Requires the disposable resume_writer_test pgvector database")
    for key, value in {
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": port,
        "POSTGRES_USER": "resume_writer_test",
        "POSTGRES_DB": "resume_writer_test",
        "POSTGRES_PASSWORD": "resume_writer_test",
    }.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(Connection, "_pool", None)
    monkeypatch.setattr(Connection, "_pool_init_lock", None)
    monkeypatch.setattr(Connection, "_role_pools", {})
    runtime = DatabaseRuntime()
    runtime.start()
    try:
        yield runtime
    finally:
        runtime.close()


def test_writer_persists_sections_and_replaces_resume_without_duplicates(pg_runtime):
    discord_id = str(uuid4().int)
    name = f"Candidate {uuid4().hex}"
    event = event_for(discord_id, name)
    resume = event["data"]["resume"]
    first = writer.handle_resume_write(event, db_runtime=pg_runtime)
    user_id = first["user_id"]
    users = pg_runtime.run(query_rows("SELECT name FROM public.users WHERE discord_id = $1", [discord_id]))
    assert users == [{"name": name}]
    for column in crud.VECTOR_COLUMNS:
        np.testing.assert_array_equal(first[column], getattr(resume, column))

    resume.name = None  # Discord ID is sufficient for an existing user.
    resume.skills_vector = None
    resume.overall_vector = resume.titles_vector
    assert writer.handle_resume_write(event, db_runtime=pg_runtime)["user_id"] == user_id
    assert event["request_id"] == "request-test"
    stored = pg_runtime.run(query_rows("SELECT * FROM public.resumes WHERE user_id = $1", [user_id]))
    assert len(stored) == 1
    assert stored[0]["skills_vector"] is None
    for column in crud.VECTOR_COLUMNS[1:]:
        np.testing.assert_array_equal(stored[0][column], getattr(resume, column))


def test_writer_matches_normalized_name_and_rejects_ambiguity_and_conflicts(pg_runtime):
    suffix = uuid4().hex
    name = f"Candidate {suffix}"
    discord_id = str(uuid4().int)
    user = pg_runtime.run(query_rows(
        "INSERT INTO public.users (name) VALUES ($1) RETURNING user_id", [name],
    ))[0]
    matching = event_for(discord_id, f" candidate  {suffix.upper()} ")
    assert writer.handle_resume_write(matching, db_runtime=pg_runtime)["user_id"] == user["user_id"]

    conflicting_id = str(uuid4().int)
    assert writer.handle_resume_write(event_for(conflicting_id, name), db_runtime=pg_runtime) is None
    pg_runtime.run(query_rows("INSERT INTO public.users (name) VALUES ($1)", [name]))
    ambiguous_id = str(uuid4().int)
    assert writer.handle_resume_write(event_for(ambiguous_id, name), db_runtime=pg_runtime) is None
    users = pg_runtime.run(query_rows(
        "SELECT discord_id FROM public.users WHERE name = $1 ORDER BY user_id", [name],
    ))
    assert users == [{"discord_id": discord_id}, {"discord_id": None}]


def test_writer_rolls_back_both_changes_when_transaction_fails(pg_runtime, monkeypatch):
    discord_id = str(uuid4().int)
    event = event_for(discord_id, f"Candidate {uuid4().hex}")
    upsert = writer.upsert_resume
    written = []

    async def fail_after_upsert(record, *, connection):
        written.append((await upsert(record, connection=connection))["user_id"])
        raise RuntimeError("private test error")

    with monkeypatch.context() as test:
        test.setattr(writer, "upsert_resume", fail_after_upsert)
        assert writer.handle_resume_write(event, db_runtime=pg_runtime) is None
    user_id, = written
    assert pg_runtime.run(query_rows("SELECT user_id FROM public.users WHERE discord_id = $1", [discord_id])) == []
    assert pg_runtime.run(query_rows("SELECT * FROM public.resumes WHERE user_id = $1", [user_id])) == []
    assert writer.handle_resume_write(event, db_runtime=pg_runtime)["user_id"] != user_id
