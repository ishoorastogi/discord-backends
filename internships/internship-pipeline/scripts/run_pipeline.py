"""Create URL-only internship objects from the sample data and write a report."""

from pathlib import Path
import sys

import requests

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
if str(PIPELINE_ROOT) not in sys.path:
    sys.path.insert(0, str(PIPELINE_ROOT))

from models.Internship import Internship
from scripts.internship_factory import create_internships
from scripts.job_page_scraper import scrape_job_page
from scripts.output_writer import OUTPUT_PATH, write_internship_report
from scripts.sample_data_loader import SAMPLE_INTERNSHIPS_PATH, load_sample_internships


def create_sample_internships(
    input_path: Path = SAMPLE_INTERNSHIPS_PATH,
) -> list[Internship]:
    records = load_sample_internships(input_path)
    return create_internships(records)


def run_pipeline(
    input_path: Path = SAMPLE_INTERNSHIPS_PATH,
    output_path: Path = OUTPUT_PATH,
) -> None:
    write_internship_report([], output_path)
    internships = create_sample_internships(input_path)
    for internship in internships:
        try:
            internship.raw_string = scrape_job_page(internship.application_url)
        except requests.RequestException as error:
            internship.scrape_error = str(error)
    write_internship_report(internships, output_path)


if __name__ == "__main__":
    run_pipeline()
    print(f"Internship report written to {OUTPUT_PATH}")
