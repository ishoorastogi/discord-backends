import pytest

from resume_parser import Resume, ResumeFactory, parse_resume_text
from resume_parser.exceptions import EmptyResumeTextError


def test_resume_factory_creates_resume_object():
    resume = ResumeFactory().create_resume("  Resume content  ")

    assert isinstance(resume, Resume)
    assert resume.raw_text == "Resume content"


def test_resume_factory_rejects_empty_text():
    with pytest.raises(EmptyResumeTextError):
        ResumeFactory().create_resume(" \n ")


def test_parse_resume_text_returns_resume_object():
    resume = parse_resume_text("  Resume content  ")

    assert isinstance(resume, Resume)
    assert resume.raw_text == "Resume content"


def test_parse_resume_text_rejects_empty_text():
    with pytest.raises(EmptyResumeTextError):
        parse_resume_text(" \n ")
