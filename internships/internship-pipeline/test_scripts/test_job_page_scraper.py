"""Check HTML extraction and bounded fetching without external network calls."""

from importlib import import_module
from unittest.mock import Mock
import json

import pytest

scraper = import_module("internships.internship-pipeline.scripts.job_page_scraper")


def test_structured_posting_text_flows_into_extraction():
    posting = {"@type": "JobPosting", "title": "Firmware Intern", "description": "<p>Build firmware.</p><h2>Required Skills</h2><p>C++, Python</p>"}
    html = '<script type="application/ld+json">' + json.dumps(posting) + '</script><nav>Noise</nav>'
    text = scraper.extract_visible_text(html)
    assert "Noise" not in text
    Internship = import_module("internships.internship-pipeline.models.Internship").Internship
    extract = import_module("internships.internship-pipeline.scripts.internship_extractor").extract_internship_data
    internship = extract(Internship(application_url="https://example.com", raw_string=text))
    assert internship.title == "Firmware Intern"
    assert internship.required_skills == ["C++", "Python"]


def test_visible_text_excludes_navigation_and_scripts():
    text = scraper.extract_visible_text('<nav>Noise</nav><main><h1>Intern</h1><p>Build APIs.</p><script>SECRET</script></main>')
    assert text == "Intern\nBuild APIs."


@pytest.mark.parametrize("url", ["file:///tmp/a", "not-a-url", "ftp://example.com", "https://"])
def test_invalid_urls_are_not_fetched(url, monkeypatch):
    fetch = Mock()
    monkeypatch.setattr(scraper.requests, "get", fetch)
    with pytest.raises(ValueError):
        scraper.scrape_job_page(url)
    fetch.assert_not_called()


def test_http_failure_propagates(monkeypatch):
    response = Mock()
    response.raise_for_status.side_effect = scraper.requests.HTTPError("unavailable")
    fetch = Mock()
    fetch.return_value.__enter__ = Mock(return_value=response)
    fetch.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(scraper.requests, "get", fetch)
    with pytest.raises(scraper.requests.HTTPError):
        scraper.scrape_job_page("https://example.com")
    response.iter_content.assert_not_called()


def test_response_limit_is_enforced(monkeypatch):
    response = Mock()
    response.iter_content.return_value = [b"123", b"456"]
    fetch = Mock()
    fetch.return_value.__enter__ = Mock(return_value=response)
    fetch.return_value.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(scraper.requests, "get", fetch)
    monkeypatch.setattr(scraper, "MAX_RESPONSE_BYTES", 5)
    with pytest.raises(scraper.requests.RequestException, match="exceeds"):
        scraper.scrape_job_page("https://example.com")
