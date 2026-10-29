"""Shared logging isolation for internship service tests."""

import io
import logging
import os
import unittest
from unittest.mock import patch

from shared.logs import log_config


LOGGER_NAMES = ("event_queue", "test_logging", "processor", "tcp_listener", "event_router", "main", "intake handler", "resume handler", "internship handler")


def reset_logging():
    handlers = set(log_config._handlers or [])
    for name in LOGGER_NAMES:
        logger = logging.getLogger(name)
        handlers.update(logger.handlers)
        logger.handlers.clear()
    for handler in handlers:
        handler.close()
    log_config._handlers = None
    log_config._level = logging.INFO


class BaseTest(unittest.TestCase):
    def setUp(self):
        reset_logging()
        environment = patch.dict(os.environ, {"LOG_LEVEL": "INFO", "LOG_FILE": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.addCleanup(reset_logging)
        self.output = io.StringIO()
        stderr = patch("sys.stderr", self.output)
        stderr.start()
        self.addCleanup(stderr.stop)
        for name in LOGGER_NAMES:
            log_config.get_logger(name)


