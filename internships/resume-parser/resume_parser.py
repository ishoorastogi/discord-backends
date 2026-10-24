"""Public API for the flat resume parser modules."""

from internships.models import Resume
from parser import parse_resume_base64, parse_resume_pdf, parse_resume_text

__all__ = [
    "Resume",
    "parse_resume_base64",
    "parse_resume_pdf",
    "parse_resume_text",
]
