"""Convert extracted resume text into a Resume object."""

from pathlib import Path

from resume_parser.exceptions import EmptyResumeTextError
from resume_parser.models import Resume
from resume_parser.pdf_reader import extract_pdf_text


def parse_resume_text(text: str) -> Resume:
    """Create a Resume object from extracted text."""
    if not text.strip():
        raise EmptyResumeTextError("Resume text cannot be empty.")

    return Resume(raw_text=text.strip())


def parse_resume_pdf(pdf_path: Path) -> Resume:
    """Extract text from a PDF and return it as a Resume object."""
    return parse_resume_text(extract_pdf_text(pdf_path))
