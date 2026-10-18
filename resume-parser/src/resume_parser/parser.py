"""Coordinate resume text extraction and object creation."""

from pathlib import Path

from resume_parser.factory import ResumeFactory
from resume_parser.models import Resume
from resume_parser.pdf_reader import extract_pdf_text


def parse_resume_text(text: str) -> Resume:
    """Create a Resume object from already-extracted text."""
    return ResumeFactory().create_resume(text)


def parse_resume_pdf(pdf_path: Path) -> Resume:
    """Extract text from a PDF, then create a Resume object."""
    return parse_resume_text(extract_pdf_text(pdf_path))
