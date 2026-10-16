import json

from log_config import get_logger


logger = get_logger("processor")


def process_resume_and_internship(resume: dict, internship: dict) -> None:
    logger.info(
        "resume_id=%s resume_size=%s internship_id=%s internship_size=%s",
        resume.get("id"),
        len(resume["text"]),
        internship.get("id"),
        len(json.dumps(internship)),
    )
