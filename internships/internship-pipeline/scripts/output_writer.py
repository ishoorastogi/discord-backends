"""Replace the sample text report with the current internship objects."""

from dataclasses import fields
from pathlib import Path

from models.Internship import Internship


OUTPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "test_data"
    / "internship_results.txt"
)

REPORT_METADATA = {"application_url", "job_id", "raw_string", "scrape_error"}


def _format_extracted_fields(internship: Internship) -> str:
    lines = []
    for field in fields(internship):
        if field.name in REPORT_METADATA:
            continue
        value = getattr(internship, field.name)
        if value:
            label = field.name.replace("_", " ").capitalize()
            text = ", ".join(value) if isinstance(value, list) else value
            lines.append(f"{label}: {text}\n")
    return "".join(lines)


def write_internship_report(
    internships: list[Internship], path: Path = OUTPUT_PATH
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    report = "\n\n".join(
        f"Internship {index}\n"
        f"Application URL: {internship.application_url}\n"
        f"Job ID: {internship.job_id or 'Not provided'}\n"
        f"{_format_extracted_fields(internship)}"
        f"Raw page text:\n{internship.raw_string or 'Not available'}"
        + (
            f"\nScrape error: {internship.scrape_error}"
            if internship.scrape_error
            else ""
        )
        for index, internship in enumerate(internships, start=1)
    )
    path.write_text(f"{report}\n" if report else "", encoding="utf-8")
