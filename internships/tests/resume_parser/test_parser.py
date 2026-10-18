import pytest

from exceptions import EmptyResumeTextError
from models import Resume
from parser import parse_resume_text


def test_parse_resume_text_returns_resume_object():
    resume = parse_resume_text("  Resume content  ")

    assert isinstance(resume, Resume)
    assert resume.raw_text == "Resume content"


def test_parse_resume_text_rejects_empty_text():
    with pytest.raises(EmptyResumeTextError):
        parse_resume_text(" \n ")
