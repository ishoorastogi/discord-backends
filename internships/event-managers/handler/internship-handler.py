"""Internship processing stages for structured postings.

Intake validates INTERNSHIP_SUBMIT and queues INTERNSHIP_PARSE. Parsing
copies the structured posting and forwards it to populate. Extraction,
normalization, and vectorization are explicit placeholders pending their
business logic; they do not advance events or claim processing success.
Populate logs activation and stops; scrape is also a deferred stage.
"""

#internship intake

from functools import partial

from shared.event_queue import enqueue
from shared.logs.log_config import get_logger


logger = get_logger("internship handler")


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
    logger.info("Handling INTERNSHIP_EXTRACTION event; extraction is not implemented")
    # TODO: Extract structured internship requirements once the contract is defined.


def handle_normalization(event: dict, *, internship_queue) -> None:
    logger.info("Handling INTERNSHIP_NORMALIZATION event; normalization is not implemented")
    # TODO: Implement internship normalization.


def handle_vectorization(event: dict, *, internship_queue) -> None:
    logger.info("Handling INTERNSHIP_VECTORIZATION event; vectorization is not implemented")
    # TODO: Implement internship vectorization.


def handle_populate(event: dict, *, internship_queue) -> None:
    logger.info("Internship populate function activated; population is not implemented")
    # TODO: Define the posting source and populate internship fields.


def handle_scrape(event: dict, *, internship_queue) -> None:
    logger.info("Handling INTERNSHIP_SCRAPE event; scraping is not implemented")
    # TODO: Define supported sources and scrape internship posting data.