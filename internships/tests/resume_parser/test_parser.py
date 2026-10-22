import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "resume-parser"))

from resume_parser import Resume, ResumeFactory, parse_resume_pdf, parse_resume_text
from exceptions import EmptyResumeTextError, PdfReadError


DEFAULT_PDF = (
    Path(__file__).resolve().parents[2]
    / "resume-parser"
    / "uploads"
    / "test_resume_1.pdf"
)


def main() -> int:
    """Parse a resume PDF and print its extracted text."""
    argument_parser = argparse.ArgumentParser(
        description="Parse a resume PDF and print its extracted text."
    )
    argument_parser.add_argument(
        "pdf_path",
        nargs="?",
        type=Path,
        default=DEFAULT_PDF,
        help=f"PDF file to parse (default: {DEFAULT_PDF})",
    )
    args = argument_parser.parse_args()

    if not args.pdf_path.is_file():
        argument_parser.error(f"PDF file not found: {args.pdf_path}")

    try:
        resume = parse_resume_pdf(args.pdf_path)
    except PdfReadError as exc:
        print(f"Could not parse PDF: {exc}", file=sys.stderr)
        return 1

    sys.stdout.reconfigure(errors="replace")
    print(resume.raw_text)
    return 0


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


if __name__ == "__main__":
    raise SystemExit(main())
