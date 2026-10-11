"""Run the resume parser against a PDF file."""

import argparse
import sys
from pathlib import Path

from resume_parser import parse_resume_pdf
from resume_parser.exceptions import PdfReadError


DEFAULT_PDF = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "uploads"
    / "test_resume_1.pdf"
)


def main() -> int:
    """Parse a PDF and print its extracted text."""
    argument_parser = argparse.ArgumentParser(
        description="Extract and display text from a resume PDF."
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
    print(f"Extracted text from: {args.pdf_path}\n")
    print(resume.raw_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
