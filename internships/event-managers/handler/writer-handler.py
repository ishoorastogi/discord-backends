"""Event handlers for the writer queue."""

from functools import partial

from shared.logs.log_config import get_logger

logger = get_logger("writer handler")


def register_handlers(router, *, write_queue):
    """Register supported event types for the writer queue."""
    router.register("RESUME_WRITE", partial(handle_resume_write, write_queue=write_queue))
    router.register("INTERNSHIP_WRITE", partial(handle_internship_write, write_queue=write_queue))


def handle_resume_write(event: dict, *, write_queue) -> None:
    data = event.get("data")

    if not isinstance(data, dict):
        logger.warning("Invalid resume write payload")
        return

    discord_id = data.get("discord_id")
    if not isinstance(discord_id, str) or not discord_id.isdigit():
        logger.warning("Invalid Discord ID in resume write")
        return

    logger.info("Resume write received: discord_id=%s", discord_id)
    # TODO: Implement the database write for the resume payload.
    return


def handle_internship_write(event: dict, *, write_queue) -> None:
    data = event.get("data")

    if not isinstance(data, dict):
        logger.warning("Invalid internship write payload")
        return

    logger.info("Internship write received")
    # TODO: Implement the database write for the internship payload.
    return
