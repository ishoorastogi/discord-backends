import base64

import pytest
import parser

from exceptions import EmptyResumeTextError
from models import Resume
from parser import parse_resume_text
from resume_parser import parse_resume_base64


def test_parse_resume_text_returns_resume_object():
    resume = parse_resume_text("  Resume content  ")

    assert isinstance(resume, Resume)
    assert resume.raw_text == "Resume content"


def test_parse_resume_text_rejects_empty_text():
    with pytest.raises(EmptyResumeTextError):
        parse_resume_text(" \n ")


def test_parse_resume_base64_decodes_upload_and_cleans_up(monkeypatch):
    pdf_bytes = b"test PDF bytes"
    expected_resume = Resume(raw_text="Resume content")
    parsed_paths = []

    def parse_pdf(path):
        assert path.name == "resume.pdf"
        assert path.read_bytes() == pdf_bytes
        parsed_paths.append(path)
        return expected_resume

    monkeypatch.setattr(parser, "parse_resume_pdf", parse_pdf)

    result = parse_resume_base64(base64.b64encode(pdf_bytes).decode("ascii"))

    assert result is expected_resume
    assert not parsed_paths[0].parent.exists()
