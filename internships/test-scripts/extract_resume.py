"""Extract structured resume data from a text file or standard input."""

import argparse
import json
import sys
from pathlib import Path

# Resolve the sibling extraction package when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from extraction import EmptyResumeTextError, extract_resume_data
from internships.models import Resume


if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser(
        description="Extract structured resume data from plain text."
    )
    argument_parser.add_argument(
        "text_path",
        nargs="?",
        type=Path,
        help="UTF-8 text file to extract (default: standard input)",
    )
    args = argument_parser.parse_args()

    try:
        raw_text = (
            args.text_path.read_text(encoding="utf-8")
            if args.text_path is not None
            else sys.stdin.read()
        )
        resume = Resume(raw_text=raw_text)
        extract_resume_data(resume)
    except (OSError, UnicodeError, EmptyResumeTextError) as exc:
        print(f"Could not extract resume data: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    sys.stdout.reconfigure(errors="replace")
    print(json.dumps(resume.to_dict(), indent=2))
