"""Persist completed resume uploads on the writer thread."""

from functools import partial
from importlib import import_module

from models import Resume
from shared.logs.log_config import get_logger

logger = get_logger("writer handler")
resume_queries = import_module("shared.db-utils.crud.resume_queries")
with_transaction = import_module("shared.db-utils.crud.query").with_transaction
upsert_resume = import_module("shared.db-utils.crud.resume_insert").upsert_resume
resolve_user = import_module("shared.db-utils.resolutions.user_resolve").resolve_user


def register_handlers(router, *, db_runtime):
    router.register("RESUME_WRITE", partial(handle_resume_write, db_runtime=db_runtime))


def handle_resume_write(event: dict, *, db_runtime):
    logger.info("Handling RESUME_WRITE event")

    data = event.get("data")

    if not isinstance(data, dict):
        logger.warning("Invalid RESUME_WRITE payload")
        return

    discord_id = data.get("discord_id")

    if not isinstance(discord_id, str) or not discord_id.isdigit():
        logger.warning("Invalid Discord ID in RESUME_WRITE payload")
        return

    resume = data.get("resume")
    if not isinstance(resume, Resume):
        logger.warning("Missing or invalid Resume in RESUME_WRITE payload")
        return
    attributes = vars(resume)
    if attributes.get("overall_vector") is None or any(
        column not in attributes for column in resume_queries.VECTOR_COLUMNS
    ):
        logger.warning("Incomplete resume embeddings: discord_id=%s", discord_id)
        return

    vectors = {column: attributes[column] for column in resume_queries.VECTOR_COLUMNS}
    try:
        vectors = dict(resume_queries.resume_fields(vectors, require_user_id=False))
    except (TypeError, ValueError, OverflowError) as error:
        logger.warning(
            "Invalid resume embeddings: discord_id=%s exception_type=%s",
            discord_id, type(error).__name__,
        )
        return

    async def write_resume(conn):
        try:
            user_id = await resolve_user(discord_id, resume.name, connection=conn)
        except Exception as error:
            logger.warning(
                "RESUME_WRITE user resolution failed: discord_id=%s exception_type=%s",
                discord_id, type(error).__name__,
            )
            raise
        return await upsert_resume({"user_id": user_id, **vectors}, connection=conn)

    try:
        result = db_runtime.run(with_transaction(write_resume))
    except Exception as error:
        logger.error(
            "RESUME_WRITE transaction failed: discord_id=%s exception_type=%s",
            discord_id, type(error).__name__,
        )
        return

    logger.info(
        "Resume successfully written for user_id=%s",
        result["user_id"],
    )

    return result
