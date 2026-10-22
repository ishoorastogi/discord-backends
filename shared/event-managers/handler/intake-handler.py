"""Event handlers for the intake queue."""

import processor
from shared.event_queue import enqueue
from shared.logs.log_config import get_logger

logger = get_logger("intake handler")

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


def handle_legacy_event(event: dict) -> None:
    processor.process_resume_and_internship(event["resume"], event["internship"])


def process_event(event: dict, *, router) -> None:
    if "event" in event:
        router.route(event)
    else:
        handle_legacy_event(event)
