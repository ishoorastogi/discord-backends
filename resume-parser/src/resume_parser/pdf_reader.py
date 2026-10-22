"""PDF text extraction."""
# Reconfig: Decode base64 instead of extracting text from PDF files

from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Union

from pypdf import PdfReader
from pypdf.errors import PdfReadError as PypdfReadError

from resume_parser.exceptions import PdfReadError


PdfSource = Union[Path, BinaryIO]


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract layout-aware text from a PDF, raising PdfReadError on failure."""
    return _extract_pdf_text(pdf_path, f"PDF file: {pdf_path}")


def extract_pdf_text_from_bytes(pdf_content: bytes) -> str:
    """Extract layout-aware text from PDF bytes."""
    return _extract_pdf_text(BytesIO(pdf_content), "PDF data")


def _extract_pdf_text(pdf_source: PdfSource, source_description: str) -> str:
    try:
        reader = PdfReader(pdf_source)
        text = "\n".join(
            page.extract_text(extraction_mode="layout") or ""
            for page in reader.pages
        ).strip()
    except (OSError, ValueError, PypdfReadError) as exc:
        raise PdfReadError(f"Could not read {source_description}") from exc

    if not text:
        raise PdfReadError(f"No extractable text found in {source_description}")

    return text
