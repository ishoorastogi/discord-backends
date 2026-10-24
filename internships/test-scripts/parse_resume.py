"""Parse a resume PDF and print its raw text."""

import argparse
import sys
from pathlib import Path

# Resolve the sibling parser modules when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "resume-parser"))

from exceptions import PdfReadError
from parser import parse_resume_pdf


DEFAULT_PDF = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "uploads"
    / "SWE_Resume_Template.pdf"
)

if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser(
        description="Parse a resume PDF and print its raw text."
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
        raise SystemExit(1) from exc

    sys.stdout.reconfigure(errors="replace")
    print(resume.raw_text)
