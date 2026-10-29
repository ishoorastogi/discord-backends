"""Convert resume text, PDF files, or base64 uploads into a Resume object."""

import base64
import binascii
from pathlib import Path
from tempfile import TemporaryDirectory

from exceptions import EmptyResumeTextError, PdfReadError
from models import Resume
from pdf_reader import extract_pdf_text


def parse_resume_text(text: str) -> Resume:
    """Create a Resume object from extracted text."""
    if not text.strip():
        raise EmptyResumeTextError("Resume text cannot be empty.")

    return Resume(raw_text=text.strip())


def parse_resume_pdf(pdf_path: Path) -> Resume:
    """Extract text from a PDF and return it as a Resume object."""
    return parse_resume_text(extract_pdf_text(pdf_path))


def parse_resume_base64(pdf_base64: str) -> Resume:
    """Decode an uploaded PDF and parse it, cleaning up the temporary file."""
    if not isinstance(pdf_base64, str) or not pdf_base64:
        raise PdfReadError("PDF content must be a nonempty base64 string.")

    try:
        pdf_bytes = base64.b64decode(pdf_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise PdfReadError("Invalid base64 PDF content.") from error

    # Keep the temporary filename independent of upload metadata.
    with TemporaryDirectory(prefix="resume-parse-") as directory:
        pdf_path = Path(directory) / "resume.pdf"
        pdf_path.write_bytes(pdf_bytes)
        return parse_resume_pdf(pdf_path)
