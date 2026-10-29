"""Resume processing event handlers."""

from functools import partial

from exceptions import ResumeParserError
from internships.extraction import EmptyResumeTextError, extract_resume_data
from internships.models import Resume
from resume_parser import parse_resume_base64
from shared.event_queue import enqueue
from shared.logs.log_config import get_logger

logger = get_logger("resume handler")

def register_handlers(router, *, resume_queue):
    router.register("PARSE", partial(handle_parse, resume_queue=resume_queue))
    router.register("EXTRACTION", partial(handle_extraction, resume_queue=resume_queue))
    router.register("NORMALIZATION", partial(handle_normalization, resume_queue=resume_queue))
    router.register("VECTORIZATION", partial(handle_vectorization, resume_queue=resume_queue))
    # router.register("WRITE", partial(handle_send_to_writer)) #dbs write queue))

def handle_parse(event: dict, *, resume_queue):
    data = event.get("data")

    if not isinstance(data, dict):
        logger.warning("Invalid parse upload payload")
        return

    discord_id = data.get("discord_id")
    if not isinstance(discord_id, str) or not discord_id.isdigit():
        logger.warning("Invalid Discord ID in parse upload")
        return

    try:
        resume = parse_resume_base64(data.get("pdf_base64"))
    except (OSError, ResumeParserError) as error:
        logger.warning(
            "Resume parsing failed: discord_id=%s exception_type=%s",
            discord_id, type(error).__name__,
        )
        return

    extraction_event = {
        **event,
        "event": "EXTRACTION",
        "data": {**data, "resume": resume},
    }

    if enqueue(resume_queue, extraction_event):
        logger.info("Resume parsing successful for discord ID %s", discord_id)
    return

def handle_extraction(event: dict, *, resume_queue):
    logger.info("Handling EXTRACTION event")
    data = event.get("data")
    if not isinstance(data, dict):
        logger.warning("Invalid extraction payload")
        return

    discord_id = data.get("discord_id")
    if not isinstance(discord_id, str) or not discord_id.isdigit():
        logger.warning("Invalid Discord ID in extraction payload")
        return

    resume = data.get("resume")
    if not isinstance(resume, Resume) or not isinstance(resume.raw_text, str):
        logger.warning("Missing or invalid resume in extraction payload: discord_id=%s", discord_id)
        return

    try:
        extract_resume_data(resume)
    except EmptyResumeTextError as error:
        logger.warning(
            "Resume extraction failed: discord_id=%s exception_type=%s",
            discord_id, type(error).__name__,
        )
        return

    normalization_event = {
        **event,
        "event": "NORMALIZATION",
    }

    if enqueue(resume_queue, normalization_event):
        logger.info("Moving to NORMALIZATION stage: discord_id=%s", discord_id)

def handle_normalization(event: dict, *, resume_queue):
    logger.info("Handling NORMALIZATION event")
    #TODO: Implement the logic to handle the NORMALIZATION event
    if enqueue(resume_queue, event):
        logger.info("Moving to VECTORIZATION stage: discord_id=%s", event.get("data", {}).get("discord_id"))

def handle_vectorization(event: dict, *, resume_queue):
    logger.info("Handling VECTORIZATION event")
    #TODO: Implement the logic to handle the VECTORIZATION event

# def handle_send_to_writer(event: dict, *): #insert dbs queue here
#     logger.info("Handling WRITE event")
#     #TODO: Implement the logic to handle the WRITE event
