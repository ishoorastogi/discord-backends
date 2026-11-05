"""Internship events: parse, populate, extract, and hand off to normalization.

Populate builds the shared Internship from supplied raw_string or description.
Feed-only postings are scraped before extraction.
Normalization and vectorization remain placeholders.
"""

#internship intake

from functools import partial
from importlib import import_module

from requests import RequestException

from shared.event_queue import enqueue
from shared.logs.log_config import get_logger


logger = get_logger("internship handler")
Internship = import_module("internships.internship-pipeline.models.Internship").Internship
extract_internship_data = import_module(
    "internships.internship-pipeline.scripts.internship_extractor"
).extract_internship_data
scrape_job_page = import_module(
    "internships.internship-pipeline.scripts.job_page_scraper"
).scrape_job_page


def register_handlers(router, *, internship_queue):
    router.register("INTERNSHIP_POPULATE", partial(handle_populate, internship_queue=internship_queue))
    router.register("INTERNSHIP_SCRAPE", partial(handle_scrape, internship_queue=internship_queue))
    router.register("INTERNSHIP_PARSE", partial(handle_parse, internship_queue=internship_queue))
    router.register("INTERNSHIP_EXTRACTION", partial(handle_extraction, internship_queue=internship_queue))
    router.register("INTERNSHIP_NORMALIZATION", partial(handle_normalization, internship_queue=internship_queue))
    router.register("INTERNSHIP_VECTORIZATION", partial(handle_vectorization, internship_queue=internship_queue))


def handle_parse(event: dict, *, internship_queue) -> None:
    """Prepare an already structured posting for populate, preserving metadata."""
    data = event.get("data")
    if not isinstance(data, dict):
        logger.warning("Invalid internship parse payload")
        return

    internship = data.get("internship")
    if not isinstance(internship, dict):
        logger.warning("Missing or invalid internship in parse payload")
        return

    # Feed postings have role/applicationUrl and may not have descriptions yet.
    required_fields = (
        ("id", "company", "role", "applicationUrl")
        if "role" in internship else ("id", "title", "company", "description")
    )
    for field in required_fields:
        value = internship.get(field)
        if not isinstance(value, str) or not value.strip():
            logger.warning("Missing or invalid internship parse field: field=%s", field)
            return

    populate_event = {
        **event,
        "event": "INTERNSHIP_POPULATE",
        "data": {**data, "internship": {**internship}},
    }
    if enqueue(internship_queue, populate_event):
        logger.info("Internship posting prepared for populate")


def handle_extraction(event: dict, *, internship_queue) -> None:
    logger.info("Handling INTERNSHIP_EXTRACTION event")
    data = event.get("data")
    if not isinstance(data, dict):
        logger.warning("Invalid internship extraction payload")
        return
    internship = data.get("internship")
    if not isinstance(internship, Internship):
        logger.warning("Missing or invalid internship object in extraction payload")
        return
    if not isinstance(internship.raw_string, str) or not internship.raw_string.strip():
        logger.warning("Missing or invalid internship text in extraction payload")
        return

    extract_internship_data(internship)
    normalization_event = {**event, "event": "INTERNSHIP_NORMALIZATION"}
    if enqueue(internship_queue, normalization_event):
        logger.info("Moving to INTERNSHIP_NORMALIZATION stage")


def handle_normalization(event: dict, *, internship_queue) -> None:
    logger.info("Handling INTERNSHIP_NORMALIZATION event; normalization is not implemented")
    # TODO: Implement internship normalization.


def handle_vectorization(event: dict, *, internship_queue) -> None:
    logger.info("Handling INTERNSHIP_VECTORIZATION event; vectorization is not implemented")
    # TODO: Implement internship vectorization.


def handle_populate(event: dict, *, internship_queue) -> None:
    logger.info("Internship populate function activated")
    data = event.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("internship"), dict):
        logger.warning("Invalid internship populate payload")
        return
    posting = data["internship"]
    raw_text = posting.get("raw_string", posting.get("description"))
    if raw_text is not None and not isinstance(raw_text, str):
        logger.warning("Invalid internship posting text")
        return
    internship = Internship(
        application_url=posting.get("applicationUrl", posting.get("url", "")),
        job_id=posting.get("id"),
        raw_string=raw_text,
        title=posting.get("role", posting.get("title")),
        company=posting.get("company"),
        location=posting.get("location"),
        date_posted=str(posting["datePosted"]) if posting.get("datePosted") is not None else None,
    )
    next_stage = "INTERNSHIP_EXTRACTION" if raw_text and raw_text.strip() else "INTERNSHIP_SCRAPE"
    next_event = {
        **event,
        "event": next_stage,
        "data": {**data, "internship": internship, "internship_posting": posting},
    }
    if enqueue(internship_queue, next_event):
        logger.info("Moving to %s stage", next_stage)


def handle_scrape(event: dict, *, internship_queue) -> None:
    logger.info("Handling INTERNSHIP_SCRAPE event")
    data = event.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("internship"), Internship):
        logger.warning("Invalid internship scrape payload")
        return
    internship = data["internship"]
    if not isinstance(internship.application_url, str) or not internship.application_url.strip():
        logger.warning("Missing internship application URL")
        return
    try:
        raw_text = scrape_job_page(internship.application_url)
    except (RequestException, ValueError, OSError) as error:
        internship.scrape_error = type(error).__name__
        logger.warning("Internship scraping failed: exception_type=%s", type(error).__name__)
        return
    if not isinstance(raw_text, str) or not raw_text.strip():
        internship.scrape_error = "EmptyPostingText"
        logger.warning("Internship scraping failed: empty posting text")
        return
    internship.raw_string = raw_text
    internship.scrape_error = None
    extraction_event = {**event, "event": "INTERNSHIP_EXTRACTION"}
    if enqueue(internship_queue, extraction_event):
        logger.info("Internship scraping successful; moving to INTERNSHIP_EXTRACTION stage")