"""Fetch an application page and return its job-posting text as a string."""

import json
import re
from typing import Iterator
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


REQUEST_TIMEOUT_SECONDS = 20
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
USER_AGENT = "InternshipDescriptionPipeline/1.0"


def scrape_job_page(application_url: str) -> str:
    parsed_url = urlparse(application_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise ValueError("Application URL must be an absolute HTTP or HTTPS URL")

    with requests.get(
        application_url,
        headers={"User-Agent": USER_AGENT},
        timeout=REQUEST_TIMEOUT_SECONDS,
        stream=True,
    ) as response:
        response.raise_for_status()
        content = bytearray()
        for chunk in response.iter_content(chunk_size=64 * 1024):
            content.extend(chunk)
            if len(content) > MAX_RESPONSE_BYTES:
                raise requests.RequestException(
                    f"Page response exceeds {MAX_RESPONSE_BYTES} bytes"
                )
        encoding = response.encoding or response.apparent_encoding or "utf-8"

    return extract_visible_text(bytes(content).decode(encoding, errors="replace"))


def extract_visible_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    description = soup.select_one(".show-more-less-html__markup")
    if description and soup.select_one(".top-card-layout__title"):
        lines = []
        for label, selector in (
            ("Title", ".top-card-layout__title"),
            ("Company", ".topcard__org-name-link"),
            ("Location", ".topcard__flavor--bullet"),
            ("Date posted", ".posted-time-ago__text"),
        ):
            element = soup.select_one(selector)
            if element and (value := element.get_text(" ", strip=True)):
                lines.append(f"{label}: {value}")
        for criterion in soup.select(".description__job-criteria-item"):
            heading = criterion.select_one(".description__job-criteria-subheader")
            value = criterion.select_one(".description__job-criteria-text")
            if heading and value and heading.get_text(strip=True).casefold() == "employment type":
                lines.append(f"Employment type: {value.get_text(' ', strip=True)}")
                break
        return "\n".join([*lines, "Description:", _block_text(description)])

    structured_text = _extract_job_posting_text(soup)
    if structured_text:
        return structured_text

    for element in soup(
        ["script", "style", "noscript", "svg", "template", "header", "footer", "nav", "aside"]
    ):
        element.decompose()

    main_content = soup.find(["main", "article"])
    content = main_content if main_content else soup.body or soup
    return content.get_text(separator="\n", strip=True)


def _extract_job_posting_text(soup: BeautifulSoup) -> str | None:
    for script in soup.find_all("script", type="application/ld+json"):
        raw_json = script.string or script.get_text(strip=True)
        try:
            data = json.loads(raw_json)
        except json.JSONDecodeError:
            continue

        for value in _walk_json(data):
            if not _is_job_posting(value.get("@type")):
                continue
            lines = []
            for key, label in (
                ("title", "Title"),
                ("description", "Description"),
            ):
                text = _json_value_text(value.get(key))
                if text:
                    lines.append(f"{label}:\n{text}" if key == "description" else f"{label}: {text}")
            if lines:
                return "\n\n".join(lines)
    return None


def _walk_json(value: object) -> Iterator[dict[str, object]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _is_job_posting(value: object) -> bool:
    types = value if isinstance(value, list) else [value]
    return any(
        isinstance(item, str) and item.rstrip("/").rsplit("/", 1)[-1] == "JobPosting"
        for item in types
    )


def _json_value_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, dict):
        preferred_keys = (
            "name",
            "streetAddress",
            "addressLocality",
            "addressRegion",
            "postalCode",
            "addressCountry",
        )
        values = [_json_value_text(value[key]) for key in preferred_keys if key in value]
        result = ", ".join(item for item in values if item)
        return result or None
    if isinstance(value, list):
        values = [_json_value_text(item) for item in value]
        result = "; ".join(item for item in values if item)
        return result or None
    return _block_text(BeautifulSoup(str(value), "html.parser")) or None


def _block_text(content) -> str:
    for element in content.find_all(
        ["br", "div", "p", "li", "h1", "h2", "h3", "h4", "h5", "h6"]
    ):
        element.insert_before("\n")
        element.insert_after("\n")
    lines = (re.sub(r"\s+", " ", line).strip() for line in content.get_text(" ").splitlines())
    return "\n".join(line for line in lines if line)
