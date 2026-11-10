"""Manually test extraction with sample posting text and print the object."""

import argparse
from pathlib import Path
import sys


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_ROOT.parents[1]))

from importlib import import_module

Internship = import_module("internships.internship-pipeline.models.Internship").Internship
extract_internship_data = import_module(
    "internships.internship-pipeline.scripts.internship_extractor"
).extract_internship_data


# Replace this text to try a different posting without running the scraper.
SAMPLE_RAW_TEXT = """Title: Software Engineering Intern
Company: Example Co
Location: Dallas, TX
Employment type: Internship
Workplace type: Hybrid
Description:
Build tools that help teams analyze data.
Required Skills:
- Python
- SQL
- python
Preferred Skills: React, Docker
Qualifications:
Able to work with a team and communicate technical ideas.
Responsibilities:
Build APIs and dashboards.
Write tests and document your work.
Education Requirements:
Currently pursuing a degree in Computer Science or a related field.
Experience Requirements:
Experience building a software project.
Benefits: Mentorship and paid holidays.
Compensation: $25/hour
Date Posted: 2026-11-01
Job ID: EXAMPLE-123
"""


def test_internship_extractor() -> None:
    internship = Internship(
        application_url="https://example.com/jobs/EXAMPLE-123",
        raw_string=SAMPLE_RAW_TEXT,
    )

    result = extract_internship_data(internship)
    assert result is internship
    assert internship.raw_string == SAMPLE_RAW_TEXT
    assert internship.title == "Software Engineering Intern"
    assert internship.company == "Example Co"
    assert internship.required_skills == ["Python", "SQL"]
    assert internship.preferred_skills == ["React", "Docker"]
    assert internship.compensation == "$25/hour"
    print(internship)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Fetch a real posting instead of using sample text.")
    args = parser.parse_args()
    if args.url:
        scrape_job_page = import_module(
            "internships.internship-pipeline.scripts.job_page_scraper"
        ).scrape_job_page

        internship = Internship(
            application_url=args.url,
            raw_string=scrape_job_page(args.url),
        )
        extract_internship_data(internship)
        print(internship)
    else:
        test_internship_extractor()
