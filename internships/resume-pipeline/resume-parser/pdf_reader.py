"""PDF text extraction."""

from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError as PypdfReadError

from exceptions import PdfReadError


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract layout-aware text from a PDF, raising PdfReadError on failure."""
    try:
        reader = PdfReader(pdf_path)
        text = "\n".join(
            page.extract_text(extraction_mode="layout") or ""
            for page in reader.pages
        ).strip()
    except (OSError, ValueError, PypdfReadError) as exc:
        raise PdfReadError(f"Could not read PDF file: {pdf_path}") from exc

    if not text:
        raise PdfReadError(f"No extractable text found in PDF file: {pdf_path}")

    return text
