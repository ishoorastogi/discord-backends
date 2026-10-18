import json
from dataclasses import asdict
from pathlib import Path

import pytest

from resume_parser import Resume, ResumeExtractor, parse_resume_pdf, parse_resume_text
from resume_parser.exceptions import EmptyResumeTextError


def test_extract_resume_from_pdf_and_save_to_text_file():
    project_dir = Path(__file__).resolve().parents[1]
    pdf_path = project_dir / "data" / "uploads" / "SWE_Resume_Template.pdf"
    output_path = Path(__file__).with_name("resume_output.txt")

    resume = parse_resume_pdf(pdf_path)
    result = ResumeExtractor.extract(resume, resume.raw_text)

    assert result is resume
    assert resume.education
    assert resume.projects
    assert resume.skills.all()
    assert resume.experience

    output_path.write_text(json.dumps(asdict(resume), indent=2), encoding="utf-8")
    assert json.loads(output_path.read_text(encoding="utf-8"))["education"]


def test_parse_resume_text_returns_resume_object():
    resume = parse_resume_text("  Resume content  ")

    assert isinstance(resume, Resume)
    assert resume.raw_text == "Resume content"


def test_parse_resume_text_rejects_empty_text():
    with pytest.raises(EmptyResumeTextError):
        parse_resume_text(" \n ")
