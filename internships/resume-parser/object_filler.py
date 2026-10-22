"""Create resume objects from uploaded PDF data."""

from resume_parser.factory import ResumeFactory
from resume_parser.resume_obj import Resume
from resume_parser.pdf_reader import extract_pdf_text_from_bytes


def fill_resume_from_pdf(pdf_content: bytes) -> Resume:
    """Extract uploaded PDF text and create a Resume with the factory."""
    text = extract_pdf_text_from_bytes(pdf_content)
    return ResumeFactory().create_resume(text)
