"""Test URL-only internship creation and report replacement."""

import json
import requests
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


PIPELINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE_ROOT))

from models.Internship import Internship
from scripts.internship_extractor import extract_internship_data
from scripts.internship_factory import create_internships
from scripts.job_page_scraper import extract_visible_text
from scripts.output_writer import write_internship_report
from scripts.sample_data_loader import (
    SAMPLE_INTERNSHIPS_PATH,
    load_sample_internships,
)
from scripts.run_pipeline import run_pipeline


class InternshipPipelineTests(unittest.TestCase):
    def test_extractor_fills_fields_and_preserves_source(self) -> None:
        raw_string = (
            "Title: Firmware Intern\nCompany: Example Co\nLocation: Dallas, TX\n"
            "Description:\nBuild embedded systems.\n"
            "Required Skills\n- C++\n- Python, python\n"
            "Preferred Skills: Rust\nResponsibilities:\n- Test firmware\n"
            "Compensation: $25/hr"
        )
        internship = Internship(
            application_url="https://example.test/jobs/1",
            job_id="source-id",
            raw_string=raw_string,
        )

        self.assertIs(extract_internship_data(internship), internship)
        self.assertEqual(internship.raw_string, raw_string)
        self.assertEqual(internship.job_id, "source-id")
        self.assertEqual(internship.title, "Firmware Intern")
        self.assertEqual(internship.company, "Example Co")
        self.assertEqual(internship.location, "Dallas, TX")
        self.assertEqual(internship.job_description, "Build embedded systems.")
        self.assertEqual(internship.required_skills, ["C++", "Python"])
        self.assertEqual(internship.preferred_skills, ["Rust"])
        self.assertEqual(internship.responsibilities, "- Test firmware")
        self.assertEqual(internship.compensation, "$25/hr")
        self.assertIsNone(internship.date_posted)

    def test_factory_uses_only_application_url(self) -> None:
        url = "https://example.test/jobs/1"
        with tempfile.TemporaryDirectory() as temporary_directory:
            sample_path = Path(temporary_directory) / SAMPLE_INTERNSHIPS_PATH.name
            sample_path.write_text(
                json.dumps([{"applicationUrl": url, "title": "Ignored"}]),
                encoding="utf-8",
            )
            records = load_sample_internships(sample_path)

        internships = create_internships(records)

        self.assertEqual(internships, [Internship(application_url=url)])

    def test_factory_leaves_non_url_fields_unpopulated(self) -> None:
        internship = create_internships(
            [{"applicationUrl": "https://example.test/jobs/1", "title": "Ignored"}]
        )[0]

        self.assertEqual(internship.application_url, "https://example.test/jobs/1")
        self.assertIsNone(internship.title)
        self.assertIsNone(internship.company)
        self.assertIsNone(internship.required_skills)
        self.assertIsNone(internship.job_id)
        self.assertIsNone(internship.raw_string)

    def test_scraper_extracts_visible_page_text_and_skips_scripts(self) -> None:
        page_text = extract_visible_text(
            "<html><body><script>hidden secret</script>"
            "<main><h1>Firmware Intern</h1><p>Build embedded systems.</p></main>"
            "</body></html>"
        )

        self.assertEqual(page_text, "Firmware Intern\nBuild embedded systems.")
        self.assertNotIn("hidden secret", page_text)

    def test_linkedin_scraper_keeps_posting_and_excludes_related_jobs(self) -> None:
        page_text = extract_visible_text(
            '<h1 class="top-card-layout__title">Firmware Intern</h1>'
            '<a class="topcard__org-name-link">Example Co</a>'
            '<span class="topcard__flavor--bullet">Dallas, TX</span>'
            '<div class="show-more-less-html__markup">'
            '<p>Build firmware.</p><p>What You Will Do:</p><p>Test devices.</p>'
            '</div><section>Similar jobs</section>'
        )
        internship = Internship(application_url="https://example.test/jobs/1", raw_string=page_text)
        extract_internship_data(internship)

        self.assertEqual(internship.company, "Example Co")
        self.assertEqual(internship.location, "Dallas, TX")
        self.assertEqual(internship.job_description, "Build firmware.")
        self.assertEqual(internship.responsibilities, "Test devices.")
        self.assertNotIn("Similar jobs", page_text)

    def test_scraper_prefers_structured_job_posting_description(self) -> None:
        posting = {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Firmware Intern",
            "hiringOrganization": {"@type": "Organization", "name": "Example Co"},
            "description": (
                "<p>Build <strong>embedded</strong> systems.</p>"
                "<h2>Required Skills</h2><ul><li>C++</li><li>Python</li></ul>"
            ),
        }
        html = (
            '<script type="application/ld+json">'
            + json.dumps(posting)
            + "</script><body><nav>Navigation only</nav></body>"
        )

        page_text = extract_visible_text(html)

        self.assertIn("Title: Firmware Intern", page_text)
        self.assertIn("Description:\nBuild embedded systems.", page_text)
        self.assertNotIn("Navigation only", page_text)
        self.assertNotIn("Example Co", page_text)
        internship = Internship(application_url="https://example.test/jobs/1", raw_string=page_text)
        self.assertEqual(extract_internship_data(internship).required_skills, ["C++", "Python"])

    def test_report_replaces_existing_file(self) -> None:
        internship = Internship(application_url="https://example.test/jobs/1", title="Intern")
        with tempfile.TemporaryDirectory() as temporary_directory:
            report_path = Path(temporary_directory) / "test_data" / "report.txt"
            report_path.parent.mkdir()
            report_path.write_text("stale output", encoding="utf-8")

            write_internship_report([internship], report_path)
            first_report = report_path.read_text(encoding="utf-8")
            write_internship_report([], report_path)
            second_report = report_path.read_text(encoding="utf-8")

        self.assertIn("Internship 1", first_report)
        self.assertIn("Application URL: https://example.test/jobs/1", first_report)
        self.assertNotIn("stale output", first_report)
        self.assertEqual(second_report, "")

    def test_runner_scrapes_pages_into_raw_string_and_clears_previous_output(self) -> None:
        records = [{"applicationUrl": "https://example.test/jobs/1"}]
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_path = Path(temporary_directory) / "sample.json"
            output_path = Path(temporary_directory) / "test_data" / "report.txt"
            input_path.write_text(json.dumps(records), encoding="utf-8")
            output_path.parent.mkdir()
            output_path.write_text("stale output", encoding="utf-8")

            def create_after_output_was_cleared(path: Path) -> list[Internship]:
                self.assertEqual(output_path.read_text(encoding="utf-8"), "")
                return create_internships(load_sample_internships(path))

            with (
                patch(
                    "scripts.run_pipeline.create_sample_internships",
                    side_effect=create_after_output_was_cleared,
                ),
                patch(
                    "scripts.run_pipeline.scrape_job_page",
                    return_value="Firmware Intern\nBuild embedded systems.",
                ) as scrape,
            ):
                run_pipeline(input_path, output_path)
            report = output_path.read_text(encoding="utf-8")

        scrape.assert_called_once_with("https://example.test/jobs/1")
        self.assertIn("Raw page text:\nFirmware Intern\nBuild embedded systems.", report)
        self.assertIn("Title: Firmware Intern", report)
        self.assertIn("Job description: Build embedded systems.", report)
        self.assertIn("Job ID: Not provided", report)
        self.assertNotIn("stale output", report)

    def test_runner_records_scrape_failures_and_continues(self) -> None:
        records = [
            {"applicationUrl": "https://example.test/jobs/1"},
            {"applicationUrl": "https://example.test/jobs/2"},
        ]
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_path = Path(temporary_directory) / "sample.json"
            output_path = Path(temporary_directory) / "report.txt"
            input_path.write_text(json.dumps(records), encoding="utf-8")
            with patch(
                "scripts.run_pipeline.scrape_job_page",
                side_effect=[requests.RequestException("unavailable"), "Second job"],
            ):
                run_pipeline(input_path, output_path)
            report = output_path.read_text(encoding="utf-8")

        self.assertIn("Scrape error: unavailable", report)
        self.assertIn("Raw page text:\nSecond job", report)


if __name__ == "__main__":
    unittest.main()
