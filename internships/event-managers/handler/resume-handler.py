"""Resume processing event handlers."""

from functools import partial

from exceptions import ResumeParserError
from extraction import EmptyResumeTextError, extract_resume_data
from models import Resume
from model_resources import get_normalizer
from resume_parser import parse_resume_base64
from shared.event_queue import enqueue
from shared.logs.log_config import get_logger

logger = get_logger("resume handler")

def register_handlers(router, *, resume_queue, result_queue=None):
    router.register("PARSE", partial(handle_parse, resume_queue=resume_queue))
    router.register("EXTRACTION", partial(handle_extraction, resume_queue=resume_queue))
    router.register("NORMALIZATION", partial(handle_normalization, resume_queue=resume_queue))
    router.register("VECTORIZATION", partial(handle_vectorization, resume_queue=resume_queue, result_queue=result_queue))
    router.register("WRITE", partial(handle_send_to_writer))

def handle_parse(event: dict, *, resume_queue):
    logger.info("Handling PARSE event")

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

def _valid_resume_data(event):
    data = event.get("data") if isinstance(event, dict) else None
    if not isinstance(data, dict):
        return None
    discord_id = data.get("discord_id")
    if not isinstance(discord_id, str) or not discord_id.isdigit():
        return None
    if not isinstance(data.get("resume"), Resume):
        return None
    return data


def handle_normalization(event: dict, *, resume_queue):
    logger.info("Handling NORMALIZATION event")
    data = _valid_resume_data(event)
    if data is None:
        logger.warning("Invalid normalization payload")
        return
    try:
        from normalization.normalize_resume import normalize_resume
        from normalization_adapter import normalization_input
        normalizer = get_normalizer()
        try:
            normalized = normalize_resume(normalization_input(data["resume"]), normalizer)
        finally:
            # Source modules retain diagnostic histories; don't accumulate resume
            # contents indefinitely in a long-running service.
            normalizer.log.clear()
            if normalizer.extractor is not None:
                normalizer.extractor.log.clear()
    except Exception as error:
        logger.warning("Resume normalization failed: discord_id=%s exception_type=%s",
                       data["discord_id"], type(error).__name__)
        return
    data["normalized_resume"] = normalized
    if enqueue(resume_queue, {**event, "event": "VECTORIZATION"}):
        logger.info("Moving to VECTORIZATION stage: discord_id=%s", data["discord_id"])


def handle_vectorization(event: dict, *, resume_queue, result_queue=None):
    logger.info("Handling VECTORIZATION event")
    data = _valid_resume_data(event)
    if data is None or not isinstance(data.get("normalized_resume"), dict):
        logger.warning("Invalid vectorization payload")
        return
    try:
        import numpy as np
        from vectorization.resume_vectorizer import vectorize_resume
        vectors = vectorize_resume(data["normalized_resume"])
        if not vectors or "overall" not in vectors:
            raise ValueError("Missing resume vectors")
        for vector in vectors.values():
            if (not isinstance(vector, np.ndarray) or vector.shape != (384,)
                    or vector.dtype != np.float32 or not np.isfinite(vector).all()
                    or not np.isclose(np.linalg.norm(vector), 1.0, atol=1e-5)):
                raise ValueError("Invalid resume vector")
    except Exception as error:
        logger.warning("Resume vectorization failed: discord_id=%s exception_type=%s",
                       data["discord_id"], type(error).__name__)
        return
    data["resume_vectors"] = vectors
    if result_queue is None:
        from completion_results import get_result_queue
        result_queue = get_result_queue()
    completed = {**event, "event": "VECTORIZATION_COMPLETE"}
    if not enqueue(result_queue, completed):
        logger.warning("Resume completion delivery failed: result queue full discord_id=%s request_id=%s",
                       data["discord_id"], event.get("request_id"))
        return
    logger.info("Resume completion delivered: discord_id=%s request_id=%s",
                data["discord_id"], event.get("request_id"))

def handle_send_to_writer(event: dict, *): #insert dbs queue here
    logger.info("Handling WRITE event")
    #TODO: Implement the logic to handle the WRITE event
