"""Shared logging setup. Log only IDs and sizes, never event text."""

import logging
import os


_handlers = None
_level = logging.INFO


def get_logger(name: str) -> logging.Logger:
    global _handlers, _level

    logger = logging.getLogger(name)
    invalid_level = None
    if _handlers is None:
        level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
        level = getattr(logging, level_name, None)
        if level_name not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "NOTSET"}:
            invalid_level = level_name
            level = logging.INFO

        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s"
        )
        handlers = [logging.StreamHandler()]
        log_file = os.environ.get("LOG_FILE")
        if log_file:
            handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
        for handler in handlers:
            handler.setFormatter(formatter)
            handler.setLevel(level)
        _handlers = handlers
        _level = level

    logger.setLevel(_level)
    logger.propagate = False
    for handler in _handlers:
        if handler not in logger.handlers:
            logger.addHandler(handler)

    if invalid_level is not None:
        logger.warning("Invalid LOG_LEVEL %r; using INFO", invalid_level)
    return logger
