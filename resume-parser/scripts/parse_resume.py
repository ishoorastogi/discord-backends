"""Parse a resume PDF and print its structured data as JSON."""

import argparse
import json
import sys
from pathlib import Path

from resume_parser import ResumeData, ResumeExtractor, parse_resume_pdf
from resume_parser.exceptions import PdfReadError


DEFAULT_PDF = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "uploads"
    / "SWE_Resume_Template.pdf"
)

if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser(
        description="Extract structured data from a resume PDF."
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
        resume = ResumeExtractor.extract(resume, resume.raw_text)
    except PdfReadError as exc:
        print(f"Could not parse PDF: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    sys.stdout.reconfigure(errors="replace")
    data = ResumeData(
        education=resume.education,
        projects=resume.projects,
        skills=resume.skills,
        experience=resume.experience,
    )
    print(json.dumps(data.to_dict(), indent=2))
