"""Exercise resume parsing, extraction, and handoffs between processing stages."""

import base64
from importlib import import_module
from io import BytesIO
from pathlib import Path
import queue
import sys
from unittest.mock import Mock

import pytest
import parser as resume_parser
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from models import Resume

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "event-managers" / "handler"))

resume_handler = import_module("resume-handler")


@pytest.fixture
def pdf_bytes():
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    page[NameObject("/Resources")] = DictionaryObject({
        NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): DictionaryObject({
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }),
        }),
    })
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 12 Tf 72 720 Td (Private resume text) Tj ET")
    page[NameObject("/Contents")] = content
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def parse_event(pdf_bytes):
    return {
        "event": "PARSE",
        "request_id": "request-123",
        "data": {
            "discord_id": "12345",
            "filename": "../../untrusted.pdf",
            "content_type": "application/pdf",
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        },
    }


def test_parse_and_extraction_keep_the_same_resume_instance(pdf_bytes, monkeypatch):
    pending = queue.Queue()
    event = parse_event(pdf_bytes)
    parser = resume_parser.parse_resume_pdf
    parsed_paths = []
    parsed_resumes = []

    def check_temporary_pdf(path):
        assert path.name == "resume.pdf"
        assert path.read_bytes() == pdf_bytes
        parsed_paths.append(path)
        resume = parser(path)
        parsed_resumes.append(resume)
        return resume

    logger = Mock()
    monkeypatch.setattr(resume_parser, "parse_resume_pdf", check_temporary_pdf)
    monkeypatch.setattr(resume_handler, "logger", logger)

    resume_handler.handle_parse(event, resume_queue=pending)

    result = pending.get_nowait()
    assert result == {
        **event,
        "event": "EXTRACTION",
        "data": {**event["data"], "resume": parsed_resumes[0]},
    }
    assert result["data"]["resume"] is parsed_resumes[0]
    assert parsed_resumes[0].raw_text == "Private resume text"
    assert pending.empty()
    assert event["event"] == "PARSE"
    assert "resume" not in event["data"]
    assert not parsed_paths[0].parent.exists()
    assert "Private resume text" not in str(logger.mock_calls)

    resume_handler.handle_extraction(result, resume_queue=pending)
    normalization_event = pending.get_nowait()
    assert normalization_event["event"] == "NORMALIZATION"
    assert normalization_event["data"]["resume"] is parsed_resumes[0]
    assert normalization_event["data"] is result["data"]


@pytest.mark.parametrize("content", [None, "", 123, "not base64!", "é", "===="])
def test_rejects_missing_or_invalid_base64(content, monkeypatch):
    pending = queue.Queue()
    event = parse_event(b"unused")
    event["data"]["pdf_base64"] = content
    parser = Mock()
    monkeypatch.setattr(resume_parser, "parse_resume_pdf", parser)

    resume_handler.handle_parse(event, resume_queue=pending)

    assert pending.empty()
    parser.assert_not_called()


def test_unreadable_pdf_does_not_advance_and_cleans_up(monkeypatch):
    pending = queue.Queue()
    logger = Mock()
    monkeypatch.setattr(resume_handler, "logger", logger)
    parser = resume_parser.parse_resume_pdf
    parsed_paths = []

    def capture_path(path):
        parsed_paths.append(path)
        return parser(path)

    monkeypatch.setattr(resume_parser, "parse_resume_pdf", capture_path)
    resume_handler.handle_parse(parse_event(b"private invalid PDF"), resume_queue=pending)

    assert pending.empty()
    assert not parsed_paths[0].parent.exists()
    logger.warning.assert_called_once_with(
        "Resume parsing failed: discord_id=%s exception_type=%s", "12345", "PdfReadError",
    )


def test_pdf_without_text_does_not_advance():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    output = BytesIO()
    writer.write(output)
    pending = queue.Queue()

    resume_handler.handle_parse(parse_event(output.getvalue()), resume_queue=pending)

    assert pending.empty()


def test_full_queue_does_not_report_success(pdf_bytes, monkeypatch):
    pending = queue.Queue(maxsize=1)
    pending.put_nowait({"event": "EXISTING"})
    logger = Mock()
    monkeypatch.setattr(resume_handler, "logger", logger)

    resume_handler.handle_parse(parse_event(pdf_bytes), resume_queue=pending)

    assert pending.get_nowait() == {"event": "EXISTING"}
    assert pending.empty()
    logger.info.assert_not_called()


def test_extraction_enriches_the_same_resume_and_preserves_metadata(monkeypatch):
    pending = queue.Queue()
    resume = Resume(raw_text=(
        "EDUCATION\nUniversity of Example | B.S. Computer Science | May 2024\n"
        "PROJECTS\nForecast API | Python, FastAPI | Jan 2023 - Mar 2023\n"
        "SKILLS\nProgramming Languages: Python\n"
        "EXPERIENCE\nSoftware Engineer | Example Co | Jan 2022 - Dec 2023"
    ))
    event = {
        "event": "EXTRACTION",
        "request_id": "request-123",
        "data": {
            "discord_id": "12345",
            "filename": "resume.pdf",
            "resume": resume,
        },
    }
    raw_text = resume.raw_text
    logger = Mock()
    monkeypatch.setattr(resume_handler, "logger", logger)

    resume_handler.handle_extraction(event, resume_queue=pending)

    result = pending.get_nowait()
    assert result["event"] == "NORMALIZATION"
    assert result["request_id"] == "request-123"
    assert result["data"] is event["data"]
    assert result["data"]["filename"] == "resume.pdf"
    assert result["data"]["resume"] is resume
    assert resume.education[0].school == "University of Example"
    assert resume.projects[0].name == "Forecast API"
    assert resume.skills.languages == ["Python"]
    assert resume.experience[0].duration_months == 24
    assert resume.raw_text == raw_text
    assert event["event"] == "EXTRACTION"
    assert "extracted_data" not in result["data"]
    assert pending.empty()
    assert "University of Example" not in str(logger.mock_calls)


@pytest.mark.parametrize("raw_text", [None, 123, [], {}, "", " \n "])
def test_extraction_rejects_invalid_text(raw_text, monkeypatch):
    pending = queue.Queue()
    logger = Mock()
    monkeypatch.setattr(resume_handler, "logger", logger)

    resume_handler.handle_extraction({
        "event": "EXTRACTION", "data": {"discord_id": "12345", "resume": Resume(raw_text=raw_text)},
    }, resume_queue=pending)

    assert pending.empty()
    logger.warning.assert_called_once()


@pytest.mark.parametrize("resume", [None, "Resume text", {}, []])
def test_extraction_rejects_missing_or_invalid_resume_object(resume, monkeypatch):
    pending = queue.Queue()
    extract = Mock()
    monkeypatch.setattr(resume_handler, "extract_resume_data", extract)

    resume_handler.handle_extraction({
        "event": "EXTRACTION", "data": {"discord_id": "12345", "resume": resume},
    }, resume_queue=pending)

    assert pending.empty()
    extract.assert_not_called()


@pytest.mark.parametrize("data", [None, [], "invalid"])
def test_extraction_rejects_invalid_payload(data, monkeypatch):
    pending = queue.Queue()
    extract = Mock()
    monkeypatch.setattr(resume_handler, "extract_resume_data", extract)

    resume_handler.handle_extraction({"event": "EXTRACTION", "data": data}, resume_queue=pending)

    assert pending.empty()
    extract.assert_not_called()


@pytest.mark.parametrize("discord_id", [None, "", "abc", 123])
def test_extraction_rejects_invalid_discord_id(discord_id, monkeypatch):
    pending = queue.Queue()
    extract = Mock()
    monkeypatch.setattr(resume_handler, "extract_resume_data", extract)

    resume_handler.handle_extraction({
        "event": "EXTRACTION", "data": {"discord_id": discord_id, "resume": Resume(raw_text="Resume text")},
    }, resume_queue=pending)

    assert pending.empty()
    extract.assert_not_called()


def test_extraction_full_queue_does_not_report_handoff(monkeypatch):
    pending = queue.Queue(maxsize=1)
    pending.put_nowait({"event": "EXISTING"})
    logger = Mock()
    monkeypatch.setattr(resume_handler, "logger", logger)

    resume_handler.handle_extraction({
        "event": "EXTRACTION",
        "data": {"discord_id": "12345", "resume": Resume(raw_text="SKILLS\nProgramming Languages: Python")},
    }, resume_queue=pending)

    assert pending.get_nowait() == {"event": "EXISTING"}
    assert pending.empty()
    logger.info.assert_called_once_with("Handling EXTRACTION event")
