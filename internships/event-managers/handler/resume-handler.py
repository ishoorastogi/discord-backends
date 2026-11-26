"""Resume processing event handlers."""

from functools import partial
from importlib import import_module

from exceptions import ResumeParserError
from extraction import EmptyResumeTextError, extract_resume_data
from models import Resume
from model_resources import get_normalizer
from resume_parser import parse_resume_base64
from shared.event_queue import enqueue
from shared.logs.log_config import get_logger

logger = get_logger("resume handler")
resume_queries = import_module("shared.db-utils.crud.resume_queries")

def register_handlers(router, *, resume_queue, writer_queue, esco_csv=None, esco_cache_dir=None):
    router.register("PARSE", partial(handle_parse, resume_queue=resume_queue))
    router.register("EXTRACTION", partial(handle_extraction, resume_queue=resume_queue))
    router.register("NORMALIZATION", partial(handle_normalization, resume_queue=resume_queue, esco_csv=esco_csv, esco_cache_dir=esco_cache_dir,))
    router.register("VECTORIZATION", partial(handle_vectorization,  writer_queue=writer_queue))

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

    name = data.get("name")
    if resume.name is None and isinstance(name, str):
        resume.name = name.strip() or None

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


def handle_normalization(event: dict, *, resume_queue, esco_csv=None, esco_cache_dir=None):
    logger.info("Handling NORMALIZATION event")
    data = _valid_resume_data(event)
    if data is None:
        logger.warning("Invalid normalization payload")
        return
    try:
        from normalization.normalize_resume import normalize_resume
        from normalization_adapter import normalization_input
        normalizer = get_normalizer(esco_csv, esco_cache_dir)
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


def handle_vectorization(event: dict, *, writer_queue):
    logger.info("Handling VECTORIZATION event")
    data = _valid_resume_data(event)
    if data is None or not isinstance(data.get("normalized_resume"), dict):
        logger.warning("Invalid vectorization payload")
        return
    try:
        import numpy as np
        from vectorization.resume_vectorizer import vectorize_resume
        vectors = vectorize_resume(data["normalized_resume"])
        if "overall_vector" not in vectors:
            raise ValueError("Missing resume vectors")
        for column, vector in vectors.items():
            if (column not in resume_queries.VECTOR_COLUMNS
                    or not isinstance(vector, np.ndarray) or vector.shape != (resume_queries.RESUME_DIM,)
                    or vector.dtype != np.float32 or not np.isfinite(vector).all()
                    or not np.isclose(np.linalg.norm(vector), 1.0, atol=1e-5)):
                raise ValueError("Invalid resume vector")
        vector_lists = {section: vector.tolist() for section, vector in vectors.items()}
    except Exception as error:
        logger.warning("Resume vectorization failed: discord_id=%s exception_type=%s",
                       data["discord_id"], type(error).__name__)
        return
    resume = data["resume"]
    for column in resume_queries.VECTOR_COLUMNS:
        setattr(resume, column, vector_lists.get(column))

    completed = {**event, "event": "RESUME_WRITE", "data": data}
    if not enqueue(writer_queue, completed):
        logger.warning("Resume processing completion failed: writer queue full discord_id=%s request_id=%s",
                       data["discord_id"], event.get("request_id"))
        return
    logger.info("Resume processing complete: discord_id=%s request_id=%s",
                data["discord_id"], event.get("request_id"))
