"""Create resume objects from uploaded PDF data."""

from factory import ResumeFactory
from models import Resume
from pdf_reader import extract_pdf_text_from_bytes


def fill_resume_from_pdf(pdf_content: bytes) -> Resume:
    """Extract uploaded PDF text and create a Resume with the factory."""
    text = extract_pdf_text_from_bytes(pdf_content)
    return ResumeFactory().create_resume(text)
