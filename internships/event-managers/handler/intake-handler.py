"""Event handlers for the intake queue."""

import processor
from functools import partial
from urllib.parse import urlsplit
from shared.event_queue import enqueue
from shared.logs.log_config import get_logger

logger = get_logger("intake handler")

def register_handlers(router, *, resume_queue, internship_queue=None):
    router.register("RESUME_UPLOAD", partial(handle_resume_upload, resume_queue=resume_queue))
    if internship_queue is not None:
        router.register(
            "INTERNSHIP_SUBMIT",
            partial(handle_internship_submit, internship_queue=internship_queue),
        )

def handle_resume_upload(event: dict, *, resume_queue) -> None:
    data = event.get("data")

    if not isinstance(data, dict):
        logger.warning("Invalid resume upload payload")
        return

    discord_id = data.get("discord_id")
    if not isinstance(discord_id, str) or not discord_id.isdigit():
        logger.warning("Invalid Discord ID in resume upload")
        return

    logger.info("Resume upload received: discord_id=%s", discord_id)
    enqueue(resume_queue, {**event, "event": "PARSE"})
    return


def handle_internship_submit(event: dict, *, internship_queue) -> None:
    """Forward a valid posting without mutating its envelope or contents."""
    data = event.get("data")
    if not isinstance(data, dict):
        logger.warning("Invalid internship submission payload")
        return

    internship = data.get("internship")
    if not isinstance(internship, dict):
        logger.warning("Missing or invalid internship in submission")
        return

    # Feed postings have role/applicationUrl and may not have descriptions yet.
    required_fields = (
        ("id", "company", "role", "applicationUrl")
        if "role" in internship else ("id", "title", "company", "description")
    )
    for field in required_fields:
        value = internship.get(field)
        if not isinstance(value, str) or not value.strip():
            logger.warning("Missing or invalid internship field: field=%s", field)
            return

    for url_field in ("url", "applicationUrl"):
        if url_field not in internship:
            continue
        url = internship[url_field]
        if not isinstance(url, str) or not url or any(char.isspace() for char in url):
            logger.warning("Invalid internship URL")
            return
        try:
            parsed = urlsplit(url)
            valid_url = (
                parsed.scheme.lower() in ("http", "https")
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
            )
            # Accessing port also rejects malformed and out-of-range ports.
            parsed.port
        except ValueError:
            valid_url = False
        if not valid_url:
            logger.warning("Invalid internship URL")
            return

    processing_event = {**event, "event": "INTERNSHIP_PARSE"}
    if enqueue(internship_queue, processing_event):
        logger.info("Internship submission queued for processing")


def handle_legacy_event(event: dict) -> None:
    processor.process_resume_and_internship(event["resume"], event["internship"])


def process_event(event: dict, *, router) -> None:
    if "event" in event:
        router.route(event)
    else:
        handle_legacy_event(event)
