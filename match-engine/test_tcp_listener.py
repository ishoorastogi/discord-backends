import copy
import io
import json
import logging
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Keep import-time logging independent of the caller's environment.
with patch.dict(os.environ, {"LOG_LEVEL": "INFO", "LOG_FILE": ""}):
    import log_config
    import processor
    import tcp_listener


EVENT = {
    "resume": {"id": "r1", "text": "PRIVATE_RESUME_TEXT"},
    "internship": {"id": "i1", "description": "PRIVATE_INTERNSHIP_TEXT"},
}
LINE = json.dumps(EVENT).encode("utf-8") + b"\n"
LOGGER_NAMES = ("test_logging", "processor", "tcp_listener")


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


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.messages = []
        self.condition = threading.Condition()

    def emit(self, record):
        with self.condition:
            self.messages.append(self.format(record))
            self.condition.notify_all()

    def wait_for(self, predicate):
        with self.condition:
            return self.condition.wait_for(lambda: predicate(self.messages), timeout=3)


class BaseTest(unittest.TestCase):
    def setUp(self):
        reset_logging()
        self.environment = patch.dict(os.environ, {"LOG_LEVEL": "INFO", "LOG_FILE": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(reset_logging)
        self.capture = Capture()
        for name in ("processor", "tcp_listener"):
            logger = log_config.get_logger(name)
            logger.handlers = [self.capture]

    def assert_private(self, messages):
        output = "\n".join(messages)
        self.assertNotIn(EVENT["resume"]["text"], output)
        self.assertNotIn(EVENT["internship"]["description"], output)


class LoggingTests(BaseTest):
    def setUp(self):
        super().setUp()
        reset_logging()
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


class ValidationTests(BaseTest):
    def test_valid_event(self):
        self.assertIsNone(tcp_listener.validate_event(EVENT))

    def test_required_fields(self):
        for field in ("resume_missing", "resume_empty", "resume_invalid",
                      "internship_missing", "internship_empty", "internship_invalid",
                      "resume_id_missing", "resume_text_missing",
                      "resume_text_invalid", "internship_id_missing"):
            with self.subTest(field=field):
                event = copy.deepcopy(EVENT)
                if field == "resume_missing":
                    del event["resume"]
                elif field == "resume_empty":
                    event["resume"] = {}
                elif field == "resume_invalid":
                    event["resume"] = []
                elif field == "internship_missing":
                    del event["internship"]
                elif field == "internship_empty":
                    event["internship"] = {}
                elif field == "internship_invalid":
                    event["internship"] = []
                elif field == "resume_id_missing":
                    del event["resume"]["id"]
                elif field == "resume_text_missing":
                    del event["resume"]["text"]
                elif field == "resume_text_invalid":
                    event["resume"]["text"] = 123
                else:
                    del event["internship"]["id"]
                self.assertIsInstance(tcp_listener.validate_event(event), str)


class BufferTests(BaseTest):
    def test_single_line(self):
        self.assertEqual(tcp_listener.MessageBuffer().feed(LINE), [EVENT])

    def test_split_line(self):
        buffer = tcp_listener.MessageBuffer()
        self.assertEqual(buffer.feed(LINE[:10]), [])
        self.assertEqual(buffer.feed(LINE[10:]), [EVENT])

    def test_two_lines(self):
        self.assertEqual(tcp_listener.MessageBuffer().feed(LINE + LINE), [EVENT, EVENT])

    def test_empty_lines(self):
        self.assertEqual(tcp_listener.MessageBuffer().feed(b"\n\n" + LINE), [EVENT])
        self.assertEqual(self.capture.messages, [])

    def test_bad_lines_recover_and_are_private(self):
        missing = json.dumps({"resume": EVENT["resume"]}).encode() + b"\n"
        for bad in (b"PRIVATE_RESUME_TEXT\n", b"\xffPRIVATE_INTERNSHIP_TEXT\n",
                    json.dumps([EVENT]).encode() + b"\n", missing):
            with self.subTest(bad_type=bad[:1]):
                buffer = tcp_listener.MessageBuffer()
                self.assertEqual(buffer.feed(bad + LINE), [EVENT])
        self.assertEqual(len(self.capture.messages), 4)
        self.assert_private(self.capture.messages)

    def test_oversized_remainder(self):
        with self.assertRaises(tcp_listener.MessageTooLargeError):
            tcp_listener.MessageBuffer().feed(b"x" * (tcp_listener.MAX_MESSAGE_BYTES + 1))

    def test_oversized_complete_line(self):
        with self.assertRaises(tcp_listener.MessageTooLargeError):
            tcp_listener.MessageBuffer().feed(b"x" * (tcp_listener.MAX_MESSAGE_BYTES + 1) + b"\n")

    def test_close_discards_partial_with_size_only(self):
        buffer = tcp_listener.MessageBuffer()
        partial = EVENT["resume"]["text"].encode()
        buffer.feed(partial)
        buffer.close()
        self.assertEqual(self.capture.messages, [f"Discarded incomplete message: size={len(partial)}"])
        self.assertEqual(buffer.feed(LINE), [EVENT])
        buffer.close()
        self.assertEqual(len(self.capture.messages), 1)
        self.assert_private(self.capture.messages)

    def test_processor_logs_are_private(self):
        processor.process_resume_and_internship(EVENT["resume"], EVENT["internship"])
        self.assertEqual(self.capture.messages, [
            f"resume_id=r1 resume_size={len(EVENT['resume']['text'])} "
            f"internship_id=i1 internship_size={len(json.dumps(EVENT['internship']))}"
        ])
        self.assert_private(self.capture.messages)


class ServerTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.clients = []
        self.server = tcp_listener.create_server("127.0.0.1", 0)
        self.thread = threading.Thread(
            target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        )
        self.thread.start()

    def tearDown(self):
        for client in self.clients:
            client.close()
        try:
            self.assertTrue(self.capture.wait_for(
                lambda messages: sum("Client disconnected" in m for m in messages) == len(self.clients)
            ))
        finally:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(timeout=3)
        self.assertFalse(self.thread.is_alive())
        self.assert_private(self.capture.messages)

    def connect(self):
        client = socket.create_connection(self.server.server_address, timeout=3)
        self.clients.append(client)
        return client

    def receipts(self, messages):
        return sum("resume_id=r1 " in message for message in messages)

    def wait_receipts(self, count):
        self.assertTrue(self.capture.wait_for(lambda messages: self.receipts(messages) == count))

    def test_valid_event_once(self):
        self.connect().sendall(LINE)
        self.wait_receipts(1)

    def test_split_only_after_newline(self):
        client = self.connect()
        received = threading.Event()
        original = tcp_listener.MessageBuffer.feed

        def observed_feed(buffer, data):
            result = original(buffer, data)
            received.set()
            return result

        with patch.object(tcp_listener.MessageBuffer, "feed", observed_feed):
            client.sendall(LINE[:10])
            self.assertTrue(received.wait(3))
            self.assertEqual(self.receipts(self.capture.messages), 0)
            received.clear()
            client.sendall(LINE[10:-1])
            self.assertTrue(received.wait(3))
            self.assertEqual(self.receipts(self.capture.messages), 0)
            client.sendall(b"\n")
            self.wait_receipts(1)

    def test_bad_then_valid_same_connection(self):
        self.connect().sendall(b"bad-json\n" + LINE)
        self.wait_receipts(1)
        self.assertTrue(any("invalid JSON" in message for message in self.capture.messages))

    def test_oversized_disconnect_and_new_connection(self):
        client = self.connect()
        try:
            client.sendall(b"x" * (tcp_listener.MAX_MESSAGE_BYTES + 65536))
        except ConnectionError:
            pass
        try:
            self.assertEqual(client.recv(1), b"")
        except ConnectionError:
            pass
        self.assertTrue(self.capture.wait_for(
            lambda messages: any("exceeds size limit" in message for message in messages)
        ))
        self.connect().sendall(LINE)
        self.wait_receipts(1)

    def test_partial_disconnect(self):
        client = self.connect()
        client.sendall(LINE[:10])
        client.close()
        self.assertTrue(self.capture.wait_for(
            lambda messages: any("Discarded incomplete message: size=10" in message for message in messages)
        ))
        self.connect().sendall(LINE)
        self.wait_receipts(1)

    def test_processor_exception_continues(self):
        completed = threading.Event()
        calls = []

        def fail_once(resume, internship):
            calls.append((resume, internship))
            if len(calls) == 1:
                raise RuntimeError("simulated processor failure")
            processor.process_resume_and_internship(resume, internship)
            completed.set()

        with patch("tcp_listener.process_resume_and_internship", side_effect=fail_once):
            self.connect().sendall(LINE + LINE)
            self.assertTrue(completed.wait(3))
            self.assertEqual(calls, [(EVENT["resume"], EVENT["internship"])] * 2)
            self.wait_receipts(1)
        self.assertTrue(any("RuntimeError: simulated processor failure" in m for m in self.capture.messages))


if __name__ == "__main__":
    unittest.main()
