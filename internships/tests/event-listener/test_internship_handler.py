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
intake = load_module("internship_intake_handler", "event-managers/handler/intake-handler.py")
handler = intake
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
    handler.handle_internship_upload(event, internship_queue=pending)
    assert pending.empty()


@pytest.mark.parametrize("field", ["id", "title", "company", "description"])
@pytest.mark.parametrize("value", [None, "", " \n ", 123, [], {}])
def test_required_fields_are_nonempty_strings(event, field, value):
    event["data"]["internship"][field] = value
    pending = queue.Queue()
    handler.handle_internship_upload(event, internship_queue=pending)
    assert pending.empty()


@pytest.mark.parametrize("field", ["id", "title", "company", "description"])
def test_missing_required_field_does_not_advance(event, field):
    del event["data"]["internship"][field]
    pending = queue.Queue()
    handler.handle_internship_upload(event, internship_queue=pending)
    assert pending.empty()


@pytest.mark.parametrize("url", [None, "", 123, "relative/path", "ftp://example.com", "https://", "https://[", "https://example.com:99999", "https://example.com/a b", "https://user:secret@example.com"])
def test_invalid_optional_url_does_not_advance(event, url):
    event["data"]["internship"]["url"] = url
    pending = queue.Queue()
    handler.handle_internship_upload(event, internship_queue=pending)
    assert pending.empty()


def test_url_is_optional_and_discord_id_not_required(event):
    del event["data"]["internship"]["url"]
    pending = queue.Queue()
    handler.handle_internship_upload(event, internship_queue=pending)
    assert pending.get_nowait()["event"] == "INTERNSHIP_PARSE"


def test_full_queue_does_not_report_success_or_log_payload(event, monkeypatch):
    pending = queue.Queue(maxsize=1)
    existing = {"event": "EXISTING"}
    pending.put_nowait(existing)
    logger = Mock()
    monkeypatch.setattr(handler, "logger", logger)
    handler.handle_internship_upload(event, internship_queue=pending)
    assert pending.get_nowait() is existing
    assert pending.empty()
    logger.info.assert_not_called()
    assert "PRIVATE_DESCRIPTION" not in str(logger.mock_calls)


def test_success_and_validation_logs_do_not_expose_posting(event, monkeypatch):
    logger = Mock()
    monkeypatch.setattr(handler, "logger", logger)
    handler.handle_internship_upload(event, internship_queue=queue.Queue())
    logger.info.assert_called_once()
    event["data"]["internship"]["url"] = "https://user:PRIVATE_SECRET@example.com"
    handler.handle_internship_upload(event, internship_queue=queue.Queue())
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


def test_processing_routes_reach_normalization(event):
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
    extraction_event = pending.get_nowait()
    assert extraction_event["event"] == "INTERNSHIP_EXTRACTION"
    router.route(extraction_event)
    normalization_event = pending.get_nowait()
    assert normalization_event["event"] == "INTERNSHIP_NORMALIZATION"
    router.route(normalization_event)
    assert pending.empty()


@pytest.mark.parametrize("stage", ["INTERNSHIP_NORMALIZATION", "INTERNSHIP_VECTORIZATION"])
def test_deferred_stages_do_not_advance(event, stage):
    pending = queue.Queue()
    router = router_module.EventRouter()
    processing.register_handlers(router, internship_queue=pending)
    router.route({**event, "event": stage})
    assert pending.empty()


def test_resume_only_registration_remains_compatible():
    router = router_module.EventRouter()
    pending = queue.Queue()
    intake.register_handlers(router, resume_queue=pending, internship_queue=queue.Queue())
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


def test_populate_builds_shared_object_without_logging_payload(event, monkeypatch):
    pending = queue.Queue()
    logger = Mock()
    monkeypatch.setattr(processing, "logger", logger)
    router = router_module.EventRouter()
    processing.register_handlers(router, internship_queue=pending)
    original = deepcopy(event)
    router.route({**event, "event": "INTERNSHIP_POPULATE"})
    logger.info.assert_any_call("Internship populate function activated")
    result = pending.get_nowait()
    assert result["event"] == "INTERNSHIP_EXTRACTION"
    assert isinstance(result["data"]["internship"], processing.Internship)
    assert result["data"]["internship"].raw_string == "PRIVATE_DESCRIPTION"
    assert result["data"]["internship_posting"] == event["data"]["internship"]
    assert pending.empty()
    assert event == original
    assert "PRIVATE_DESCRIPTION" not in str(logger.mock_calls)


def test_supplied_feed_scrapes_and_extracts_without_changing_postings(monkeypatch):
    import json

    path = Path(__file__).resolve().parents[2] / "test-scripts/test-data/internships.json"
    postings = json.loads(path.read_text(encoding="utf-8"))
    assert len(postings) == 5
    scrape = Mock(return_value="Required Skills: Python, SQL")
    monkeypatch.setattr(processing, "scrape_job_page", scrape)
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
        scrape_event = pending.get_nowait()
        assert scrape_event["event"] == "INTERNSHIP_SCRAPE"
        router.route(scrape_event)
        extraction_event = pending.get_nowait()
        assert extraction_event["event"] == "INTERNSHIP_EXTRACTION"
        router.route(extraction_event)
        normalized = pending.get_nowait()
        assert normalized["event"] == "INTERNSHIP_NORMALIZATION"
        assert normalized["data"]["internship"].required_skills == ["Python", "SQL"]
        assert normalized["data"]["internship_posting"] == posting
        router.route(normalized)
        assert pending.empty()
    assert postings == original
    assert scrape.call_count == 5
    assert sum(call.args[0].startswith("Internship populate function activated") for call in logger.info.call_args_list) == 5


@pytest.mark.parametrize("field", ["id", "company", "role", "applicationUrl"])
def test_feed_missing_fields_are_rejected(field):
    posting = {"id": "i1", "company": "Example", "role": "Intern", "applicationUrl": "https://example.com/job"}
    del posting[field]
    pending = queue.Queue()
    handler.handle_internship_upload({"data": {"internship": posting}}, internship_queue=pending)
    assert pending.empty()


def test_upload_script_accepts_worker_logs_before_acceptance(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "test-scripts"))
    script = load_module("internship_upload_script_test", "test-scripts/internship_upload.py")
    output = queue.Queue()
    for message in (
        "Internship posting prepared for populate",
        "Internship populate function activated",
        "Internship submission queued for processing",
    ):
        output.put(message)
    script.wait_for_stages(Mock(), output, 0.5)
    assert output.empty()


def test_internship_upload_event_uses_intake_handler(event):
    pending = queue.Queue()
    router = router_module.EventRouter()
    intake.register_handlers(router, resume_queue=queue.Queue(), internship_queue=pending)
    router.route({**event, "event": "INTERNSHIP_UPLOAD"})
    assert pending.get_nowait() == {**event, "event": "INTERNSHIP_PARSE"}
    assert pending.empty()


def test_extraction_enriches_same_object_preserves_metadata_and_text(event, monkeypatch):
    pending = queue.Queue()
    posting = event["data"]["internship"]
    posting["description"] = "Required Skills: Python, SQL, python\nCompensation: $25/hour"
    original = deepcopy(event)
    processing.handle_populate(event, internship_queue=pending)
    extraction_event = pending.get_nowait()
    internship = extraction_event["data"]["internship"]
    logger = Mock()
    monkeypatch.setattr(processing, "logger", logger)
    processing.handle_extraction(extraction_event, internship_queue=pending)
    result = pending.get_nowait()
    assert result["event"] == "INTERNSHIP_NORMALIZATION"
    assert result["data"] is extraction_event["data"]
    assert result["data"]["internship"] is internship
    assert internship.required_skills == ["Python", "SQL"]
    assert internship.compensation == "$25/hour"
    assert internship.title == posting["title"]
    assert internship.raw_string == posting["description"]
    assert result["request_id"] == event["request_id"]
    assert result["data"]["internship_posting"] == posting
    assert event == original
    assert "$25/hour" not in str(logger.mock_calls)


@pytest.mark.parametrize("value", [None, "", " \n", 123, [], {}])
def test_extraction_rejects_invalid_raw_text(value, monkeypatch):
    pending = queue.Queue()
    internship = processing.Internship(application_url="https://example.com", raw_string=value)
    extract = Mock()
    monkeypatch.setattr(processing, "extract_internship_data", extract)
    processing.handle_extraction({"data": {"internship": internship}}, internship_queue=pending)
    assert pending.empty()
    extract.assert_not_called()


@pytest.mark.parametrize("data", [None, [], {}, {"internship": {}}, {"internship": "private"}])
def test_extraction_rejects_invalid_payload(data):
    pending = queue.Queue()
    processing.handle_extraction({"data": data}, internship_queue=pending)
    assert pending.empty()


def test_extraction_full_queue_does_not_report_handoff(monkeypatch):
    pending = queue.Queue(maxsize=1)
    pending.put_nowait({"event": "EXISTING"})
    internship = processing.Internship(application_url="https://example.com", raw_string="Required Skills: Python")
    logger = Mock()
    monkeypatch.setattr(processing, "logger", logger)
    processing.handle_extraction({"data": {"internship": internship}}, internship_queue=pending)
    assert pending.get_nowait() == {"event": "EXISTING"}
    logger.info.assert_called_once_with("Handling INTERNSHIP_EXTRACTION event")


def test_populate_full_queue_does_not_report_handoff(event, monkeypatch):
    pending = queue.Queue(maxsize=1)
    pending.put_nowait({"event": "EXISTING"})
    logger = Mock()
    monkeypatch.setattr(processing, "logger", logger)
    processing.handle_populate(event, internship_queue=pending)
    logger.info.assert_called_once_with("Internship populate function activated")
    assert pending.get_nowait() == {"event": "EXISTING"}


@pytest.mark.parametrize("failure", [processing.RequestException("PRIVATE_ERROR"), ValueError("PRIVATE_ERROR"), OSError("PRIVATE_ERROR")])
def test_scrape_failure_does_not_advance_or_leak_error(failure, monkeypatch):
    pending = queue.Queue()
    internship = processing.Internship(application_url="https://example.com/job")
    monkeypatch.setattr(processing, "scrape_job_page", Mock(side_effect=failure))
    logger = Mock()
    monkeypatch.setattr(processing, "logger", logger)
    processing.handle_scrape({"data": {"internship": internship}}, internship_queue=pending)
    assert pending.empty()
    assert internship.scrape_error == type(failure).__name__
    assert "PRIVATE_ERROR" not in str(logger.mock_calls)


@pytest.mark.parametrize("text", [None, "", " \n", 123])
def test_scrape_empty_or_invalid_text_stops(text, monkeypatch):
    pending = queue.Queue()
    internship = processing.Internship(application_url="https://example.com/job")
    monkeypatch.setattr(processing, "scrape_job_page", Mock(return_value=text))
    processing.handle_scrape({"data": {"internship": internship}}, internship_queue=pending)
    assert pending.empty()
    assert internship.scrape_error == "EmptyPostingText"


def test_scrape_full_queue_keeps_object_without_claiming_handoff(monkeypatch):
    pending = queue.Queue(maxsize=1)
    pending.put_nowait({"event": "EXISTING"})
    internship = processing.Internship(application_url="https://example.com/job")
    monkeypatch.setattr(processing, "scrape_job_page", Mock(return_value="Description: text"))
    logger = Mock()
    monkeypatch.setattr(processing, "logger", logger)
    processing.handle_scrape({"data": {"internship": internship}}, internship_queue=pending)
    assert internship.raw_string == "Description: text"
    assert pending.get_nowait() == {"event": "EXISTING"}
    logger.info.assert_called_once_with("Handling INTERNSHIP_SCRAPE event")
