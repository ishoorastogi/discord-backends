import io
import logging
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared.logs import log_config


def reset_logging():
    handlers = set(log_config._handlers or [])
    logger = logging.getLogger("test_logging")
    handlers.update(logger.handlers)
    logger.handlers.clear()
    for handler in handlers:
        handler.close()
    log_config._handlers = None
    log_config._level = logging.INFO


class LoggingTests(unittest.TestCase):
    def setUp(self):
        reset_logging()
        self.addCleanup(reset_logging)
        environment = patch.dict(os.environ, {"LOG_LEVEL": "INFO", "LOG_FILE": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.console = io.StringIO()
        stderr = patch("sys.stderr", self.console)
        stderr.start()
        self.addCleanup(stderr.stop)

    def test_default_info(self):
        os.environ.pop("LOG_LEVEL", None)
        self.assertEqual(log_config.get_logger("test_logging").level, logging.INFO)

    def test_debug_level(self):
        os.environ["LOG_LEVEL"] = "DEBUG"
        logger = log_config.get_logger("test_logging")
        self.assertEqual(logger.level, logging.DEBUG)
        logger.debug("debug message")
        self.assertIn("DEBUG test_logging debug message", self.console.getvalue())

    def test_invalid_level_warns(self):
        os.environ["LOG_LEVEL"] = "invalid"
        logger = log_config.get_logger("test_logging")
        self.assertEqual(logger.level, logging.INFO)
        self.assertIn("WARNING test_logging Invalid LOG_LEVEL", self.console.getvalue())

    def test_repeated_calls_do_not_duplicate(self):
        first = log_config.get_logger("test_logging")
        second = log_config.get_logger("test_logging")
        self.assertIs(first, second)
        self.assertEqual(len(first.handlers), 1)
        first.info("one message")
        self.assertEqual(len(self.console.getvalue().splitlines()), 1)

    def test_log_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.log"
            os.environ["LOG_FILE"] = str(path)
            logger = log_config.get_logger("test_logging")
            logger.info("file message")
            self.assertIn("INFO test_logging file message", path.read_text())
            self.assertIn("file message", self.console.getvalue())
            reset_logging()

    def test_console_only_without_log_file(self):
        os.environ.pop("LOG_FILE", None)
        logger = log_config.get_logger("test_logging")
        self.assertEqual(len(logger.handlers), 1)
        self.assertNotIsInstance(logger.handlers[0], logging.FileHandler)
        logger.info("console message")
        self.assertIn("console message", self.console.getvalue())


if __name__ == "__main__":
    unittest.main()
