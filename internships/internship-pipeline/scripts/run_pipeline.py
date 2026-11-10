"""Create URL-only internship objects from the sample data and write a report."""

from importlib import import_module
from pathlib import Path
import sys

import requests

PIPELINE_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PIPELINE_ROOT.parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

Internship = import_module("internships.internship-pipeline.models.Internship").Internship
extract_internship_data = import_module(
    "internships.internship-pipeline.scripts.internship_extractor"
).extract_internship_data
create_internships = import_module(
    "internships.internship-pipeline.scripts.internship_factory"
).create_internships
scrape_job_page = import_module(
    "internships.internship-pipeline.scripts.job_page_scraper"
).scrape_job_page
output_writer = import_module("internships.internship-pipeline.scripts.output_writer")
OUTPUT_PATH = output_writer.OUTPUT_PATH
write_internship_report = output_writer.write_internship_report
sample_data_loader = import_module("internships.internship-pipeline.scripts.sample_data_loader")
SAMPLE_INTERNSHIPS_PATH = sample_data_loader.SAMPLE_INTERNSHIPS_PATH
load_sample_internships = sample_data_loader.load_sample_internships


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
        else:
            extract_internship_data(internship)
    write_internship_report(internships, output_path)


if __name__ == "__main__":
    run_pipeline()
    print(f"Internship report written to {OUTPUT_PATH}")
