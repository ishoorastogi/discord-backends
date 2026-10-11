import io
import logging
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

with patch.dict(os.environ, {"LOG_LEVEL": "INFO", "LOG_FILE": ""}):
    import log_config
    import event_queue


LOGGER_NAMES = ("event_queue", "test_logging", "processor", "tcp_listener")


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
        event_queue.logger = log_config.get_logger("event_queue")


class QueueTests(BaseTest):
    def test_fifo_order(self):
        events = [{"id": "first"}, {"id": "second"}, {"id": "third"}]
        pending = event_queue.create_queue(3)
        self.assertEqual(pending.maxsize, 3)
        for event in events:
            self.assertTrue(event_queue.enqueue(pending, event))
        self.assertEqual([pending.get_nowait() for _ in events], events)
        self.assertTrue(pending.empty())
        self.assertEqual(self.output.getvalue(), "")

    def test_full_queue_preserves_items_and_logs_size_only(self):
        pending = event_queue.create_queue(1)
        accepted = {"resume": {"text": "PRIVATE_ACCEPTED_TEXT"}}
        dropped = {"resume": {"text": "PRIVATE_RESUME_TEXT"},
                   "internship": {"description": "PRIVATE_INTERNSHIP_TEXT"}}
        self.assertTrue(event_queue.enqueue(pending, accepted))
        self.assertFalse(event_queue.enqueue(pending, dropped))
        self.assertEqual(pending.qsize(), 1)
        self.assertIs(pending.get_nowait(), accepted)
        self.assertTrue(pending.empty())
        lines = self.output.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("WARNING event_queue Event dropped: queue_size=1", lines[0])
        for text in ("PRIVATE_ACCEPTED_TEXT", "PRIVATE_RESUME_TEXT", "PRIVATE_INTERNSHIP_TEXT"):
            self.assertNotIn(text, lines[0])

    def test_nonpositive_capacity_rejected(self):
        for size in (0, -1):
            with self.subTest(size=size), self.assertRaises(ValueError):
                event_queue.create_queue(size)


class RegistryTests(BaseTest):
    def test_registration_order(self):
        registry = event_queue.HandlerRegistry()
        first = lambda event: None
        second = lambda event: None
        registry.register(first)
        registry.register(second)
        self.assertEqual(registry.handlers(), [first, second])

    def test_handlers_returns_copy(self):
        registry = event_queue.HandlerRegistry()
        handler = lambda event: None
        registry.register(handler)
        snapshot = registry.handlers()
        snapshot.clear()
        self.assertEqual(registry.handlers(), [handler])
        self.assertIsNot(registry.handlers(), registry.handlers())

    def test_noncallable_rejected(self):
        registry = event_queue.HandlerRegistry()
        with self.assertRaises(TypeError):
            registry.register(None)
        self.assertEqual(registry.handlers(), [])


if __name__ == "__main__":
    unittest.main()
