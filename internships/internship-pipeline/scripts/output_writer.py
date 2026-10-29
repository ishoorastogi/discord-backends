"""Replace the sample text report with the current internship objects."""

from pathlib import Path

from models.Internship import Internship


OUTPUT_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "test_data"
    / "internship_results.txt"
)


def write_internship_report(
    internships: list[Internship], path: Path = OUTPUT_PATH
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    report = "\n\n".join(
        f"Internship {index}\n"
        f"Application URL: {internship.application_url}\n"
        f"Job ID: {internship.job_id or 'Not provided'}\n"
        f"Raw page text:\n{internship.raw_string or 'Not available'}"
        + (
            f"\nScrape error: {internship.scrape_error}"
            if internship.scrape_error
            else ""
        )
        for index, internship in enumerate(internships, start=1)
    )
    path.write_text(f"{report}\n" if report else "", encoding="utf-8")
