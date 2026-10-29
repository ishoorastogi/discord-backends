"""Validate internship intake and its queue boundary without service wiring."""

from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import queue
import sys
from unittest.mock import Mock

import pytest


def load_module(name, relative_path):
    path = Path(__file__).resolve().parents[2] / relative_path
    spec = spec_from_file_location(name, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "event-listener"))
handler = load_module("internship_intake_handler", "event-managers/handler/intake-handler.py")
processing = load_module("internship_processing_handler", "event-managers/handler/internship-handler.py")
router_module = load_module("internship_test_router", "event-managers/router/event_router.py")


@pytest.fixture
def event():
    return {
        "event": "INTERNSHIP_SUBMIT",
        "request_id": "request-123",
        "source": "test",
        "data": {
            "submitted_by": "user-123",
            "internship": {
                "id": "i1",
                "title": "Backend Intern",
                "company": "Example",
                "description": "PRIVATE_DESCRIPTION",
                "url": "https://example.com/jobs/123",
                "location": "Remote",
            },
        },
    }


def test_registration_and_handoff_preserve_metadata_and_resume_routes(event):
    router = router_module.EventRouter()
    resume_handlers = {}
    for name in ("PARSE", "EXTRACTION", "NORMALIZATION", "VECTORIZATION"):
        resume_handlers[name] = Mock()
        router.register(name, resume_handlers[name])
    pending = queue.Queue()
    original = deepcopy(event)
    handler.register_handlers(router, resume_queue=queue.Queue(), internship_queue=pending)
    processing.register_handlers(router, internship_queue=pending)

    router.route(event)

    result = pending.get_nowait()
    assert result == {**original, "event": "INTERNSHIP_PARSE"}
    assert result is not event
    assert result["data"] is event["data"]
    assert event == original
    assert pending.empty()
    for name, callback in resume_handlers.items():
        resume_event = {"event": name}
        router.route(resume_event)
        callback.assert_called_once_with(resume_event)


@pytest.mark.parametrize("value", [None, [], "private", 123])
@pytest.mark.parametrize("key", ["data", "internship"])
def test_invalid_payload_does_not_advance(event, key, value):
    if key == "data":
        event[key] = value
    else:
        event["data"][key] = value
    pending = queue.Queue()
    handler.handle_internship_submit(event, internship_queue=pending)
    assert pending.empty()


@pytest.mark.parametrize("field", ["id", "title", "company", "description"])
@pytest.mark.parametrize("value", [None, "", " \n ", 123, [], {}])
def test_required_fields_are_nonempty_strings(event, field, value):
    event["data"]["internship"][field] = value
    pending = queue.Queue()
    handler.handle_internship_submit(event, internship_queue=pending)
    assert pending.empty()


@pytest.mark.parametrize("field", ["id", "title", "company", "description"])
def test_missing_required_field_does_not_advance(event, field):
    del event["data"]["internship"][field]
    pending = queue.Queue()
    handler.handle_internship_submit(event, internship_queue=pending)
    assert pending.empty()


@pytest.mark.parametrize("url", [None, "", 123, "relative/path", "ftp://example.com", "https://", "https://[", "https://example.com:99999", "https://example.com/a b", "https://user:secret@example.com"])
def test_invalid_optional_url_does_not_advance(event, url):
    event["data"]["internship"]["url"] = url
    pending = queue.Queue()
    handler.handle_internship_submit(event, internship_queue=pending)
    assert pending.empty()


def test_url_is_optional_and_discord_id_not_required(event):
    del event["data"]["internship"]["url"]
    pending = queue.Queue()
    handler.handle_internship_submit(event, internship_queue=pending)
    assert pending.get_nowait()["event"] == "INTERNSHIP_PARSE"


def test_full_queue_does_not_report_success_or_log_payload(event, monkeypatch):
    pending = queue.Queue(maxsize=1)
    existing = {"event": "EXISTING"}
    pending.put_nowait(existing)
    logger = Mock()
    monkeypatch.setattr(handler, "logger", logger)
    handler.handle_internship_submit(event, internship_queue=pending)
    assert pending.get_nowait() is existing
    assert pending.empty()
    logger.info.assert_not_called()
    assert "PRIVATE_DESCRIPTION" not in str(logger.mock_calls)


def test_success_and_validation_logs_do_not_expose_posting(event, monkeypatch):
    logger = Mock()
    monkeypatch.setattr(handler, "logger", logger)
    handler.handle_internship_submit(event, internship_queue=queue.Queue())
    logger.info.assert_called_once()
    event["data"]["internship"]["url"] = "https://user:PRIVATE_SECRET@example.com"
    handler.handle_internship_submit(event, internship_queue=queue.Queue())
    logger.warning.assert_called_once()
    assert "PRIVATE_DESCRIPTION" not in str(logger.mock_calls)
    assert "PRIVATE_SECRET" not in str(logger.mock_calls)


def test_parse_prepares_posting_and_preserves_input(event):
    original = deepcopy(event)
    pending = queue.Queue()
    processing.handle_parse(event, internship_queue=pending)
    result = pending.get_nowait()
    assert result == {**original, "event": "INTERNSHIP_POPULATE"}
    assert result["data"] is not event["data"]
    assert result["data"]["internship"] is not event["data"]["internship"]
    assert event == original
    assert pending.empty()


def test_processing_routes_stop_at_unimplemented_populate(event):
    router = router_module.EventRouter()
    pending = queue.Queue()
    handler.register_handlers(router, resume_queue=queue.Queue(), internship_queue=pending)
    processing.register_handlers(router, internship_queue=pending)
    router.route(event)
    parse_event = pending.get_nowait()
    assert parse_event["event"] == "INTERNSHIP_PARSE"
    router.route(parse_event)
    populate_event = pending.get_nowait()
    assert populate_event["event"] == "INTERNSHIP_POPULATE"
    router.route(populate_event)
    assert pending.empty()


@pytest.mark.parametrize("stage", ["INTERNSHIP_NORMALIZATION", "INTERNSHIP_VECTORIZATION", "INTERNSHIP_POPULATE", "INTERNSHIP_SCRAPE"])
def test_deferred_stages_do_not_advance(event, stage):
    pending = queue.Queue()
    router = router_module.EventRouter()
    processing.register_handlers(router, internship_queue=pending)
    router.route({**event, "event": stage})
    assert pending.empty()


def test_resume_only_registration_remains_compatible():
    router = router_module.EventRouter()
    pending = queue.Queue()
    handler.register_handlers(router, resume_queue=pending)
    router.route({"event": "RESUME_UPLOAD", "data": {"discord_id": "123"}})
    assert pending.get_nowait()["event"] == "PARSE"


@pytest.mark.parametrize("data", [None, {}, {"internship": []}, {"internship": {"id": "i1"}}])
def test_parse_invalid_payload_does_not_advance(data):
    pending = queue.Queue()
    processing.handle_parse({"event": "INTERNSHIP_PARSE", "data": data}, internship_queue=pending)
    assert pending.empty()


def test_parse_full_queue_does_not_report_success(event, monkeypatch):
    pending = queue.Queue(maxsize=1)
    pending.put_nowait({"event": "EXISTING"})
    logger = Mock()
    monkeypatch.setattr(processing, "logger", logger)
    processing.handle_parse(event, internship_queue=pending)
    logger.info.assert_not_called()
    assert pending.get_nowait() == {"event": "EXISTING"}
    assert pending.empty()


def test_populate_logs_activation_without_processing_or_payload(event, monkeypatch):
    pending = queue.Queue()
    logger = Mock()
    monkeypatch.setattr(processing, "logger", logger)
    router = router_module.EventRouter()
    processing.register_handlers(router, internship_queue=pending)
    original = deepcopy(event)
    router.route({**event, "event": "INTERNSHIP_POPULATE"})
    logger.info.assert_called_once_with(
        "Internship populate function activated; population is not implemented",
    )
    assert pending.empty()
    assert event == original
    assert "PRIVATE_DESCRIPTION" not in str(logger.mock_calls)


def test_supplied_feed_reaches_populate_without_changing_postings(monkeypatch):
    import json

    path = Path(__file__).resolve().parents[2] / "test-scripts/test-data/internships.json"
    postings = json.loads(path.read_text(encoding="utf-8"))
    assert len(postings) == 5
    logger = Mock()
    monkeypatch.setattr(processing, "logger", logger)
    router = router_module.EventRouter()
    pending = queue.Queue()
    handler.register_handlers(router, resume_queue=queue.Queue(), internship_queue=pending)
    processing.register_handlers(router, internship_queue=pending)
    original = deepcopy(postings)
    for posting in postings:
        event = {"event": "INTERNSHIP_SUBMIT", "request_id": posting["id"], "data": {"internship": posting}}
        router.route(event)
        router.route(pending.get_nowait())
        populate_event = pending.get_nowait()
        assert populate_event["event"] == "INTERNSHIP_POPULATE"
        assert populate_event["request_id"] == posting["id"]
        assert populate_event["data"]["internship"] == posting
        router.route(populate_event)
        assert pending.empty()
    assert postings == original
    assert logger.info.call_count == 10  # parse and populate for each posting
    assert sum(call.args[0].startswith("Internship populate function activated") for call in logger.info.call_args_list) == 5


@pytest.mark.parametrize("field", ["id", "company", "role", "applicationUrl"])
def test_feed_missing_fields_are_rejected(field):
    posting = {"id": "i1", "company": "Example", "role": "Intern", "applicationUrl": "https://example.com/job"}
    del posting[field]
    pending = queue.Queue()
    handler.handle_internship_submit({"data": {"internship": posting}}, internship_queue=pending)
    assert pending.empty()
