import copy
import json
import logging
import os
from pathlib import Path
import socket
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "event-listener"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internships.tests.support import reset_logging

# Keep import-time logging independent of the caller's environment.
with patch.dict(os.environ, {"LOG_LEVEL": "INFO", "LOG_FILE": ""}):
    from shared.logs import log_config
    import processor
    import tcp_listener
    import event_queue


EVENT = {
    "resume": {"id": "r1", "text": "PRIVATE_RESUME_TEXT"},
    "internship": {"id": "i1", "description": "PRIVATE_INTERNSHIP_TEXT"},
}
LINE = json.dumps(EVENT).encode("utf-8") + b"\n"
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
        for name in ("processor", "tcp_listener", "event_queue"):
            logger = log_config.get_logger(name)
            logger.handlers = [self.capture]

    def assert_private(self, messages):
        output = "\n".join(messages)
        self.assertNotIn(EVENT["resume"]["text"], output)
        self.assertNotIn(EVENT["internship"]["description"], output)


class ValidationTests(BaseTest):
    def test_valid_event(self):
        self.assertIsNone(tcp_listener.validate_event(EVENT))

    def test_event_messages_need_only_a_nonempty_event_type(self):
        for event_type in ("PING", "RESUME_UPLOAD", "UNKNOWN"):
            with self.subTest(event_type=event_type):
                self.assertIsNone(tcp_listener.validate_event({"event": event_type}))

    def test_invalid_event_types_rejected(self):
        for event_type in (None, "", "  ", 123, [], {}):
            with self.subTest(event_type=event_type):
                self.assertEqual(
                    tcp_listener.validate_event({"event": event_type}),
                    "event type must be a nonempty string",
                )

    def test_non_object_events_rejected(self):
        for event in (None, [], "event", 1):
            with self.subTest(event=event):
                self.assertEqual(tcp_listener.validate_event(event), "message must be a JSON object")

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

    def test_unicode_and_escaped_newlines_survive_split_bytes(self):
        event = {"event": "RESUME_UPLOAD", "data": {"text": "Résumé\n中文"}}
        line = json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n"
        buffer = tcp_listener.MessageBuffer()
        received = []
        for byte in line:
            received.extend(buffer.feed(bytes([byte])))
        self.assertEqual(received, [event])

    def test_completed_lines_preserve_partial_next_message(self):
        buffer = tcp_listener.MessageBuffer()
        self.assertEqual(buffer.feed(LINE + LINE[:10]), [EVENT])
        self.assertEqual(buffer.feed(LINE[10:]), [EVENT])

    def test_exact_size_limit_is_accepted_excluding_newline(self):
        with patch.object(tcp_listener, "MAX_MESSAGE_BYTES", len(LINE) - 1):
            buffer = tcp_listener.MessageBuffer()
            self.assertEqual(buffer.feed(LINE[:-1]), [])
            self.assertEqual(buffer.feed(b"\n"), [EVENT])

    def test_deeply_nested_json_is_discarded_then_recovers(self):
        nested = b"[" * 2000 + b"0" + b"]" * 2000 + b"\n"
        self.assertEqual(tcp_listener.MessageBuffer().feed(nested + LINE), [EVENT])
        self.assertEqual(len(self.capture.messages), 1)
        self.assertTrue(self.capture.messages[0].startswith("Discarded message:"))

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
        self.pending = event_queue.create_queue(10)
        self.server = tcp_listener.create_server("127.0.0.1", 0, self.pending)
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

    def read_response(self, client):
        response = bytearray()
        while not response.endswith(b"\n"):
            chunk = client.recv(1)
            self.assertTrue(chunk, "connection closed before a complete response")
            response.extend(chunk)
        return json.loads(response)

    def test_ping_replies_without_using_full_queue(self):
        for number in range(10):
            self.pending.put_nowait({"queued_id": number})
        client = self.connect()
        client.sendall(b'{"event":"PING","timestamp":12345}\n')
        self.assertEqual(self.read_response(client), {"event": "PONG", "timestamp": 12345})
        self.assertEqual(self.pending.qsize(), 10)
        self.assertFalse(any("Event dropped" in message for message in self.capture.messages))

    def test_resume_upload_acknowledges_and_queues_original_event(self):
        event = {
            "event": "RESUME_UPLOAD", "request_id": "upload-1",
            "data": {"discord_id": "12345", "text": "PRIVATE_RESUME_TEXT"},
        }
        client = self.connect()
        client.sendall(json.dumps(event).encode() + b"\n")
        self.assertEqual(self.read_response(client), {
            "event": "UPLOAD_ACCEPTED", "request_id": "upload-1",
            "message": "Resume successfully received by backend",
        })
        self.assertEqual(self.pending.get(timeout=3), event)
        self.pending.task_done()
        self.assertTrue(self.pending.empty())

    def test_resume_upload_rejected_when_full_then_accepted(self):
        for number in range(10):
            self.pending.put_nowait({"queued_id": number})
        event = {"event": "RESUME_UPLOAD", "request_id": "upload-2", "data": {"discord_id": "123"}}
        line = json.dumps(event).encode() + b"\n"
        client = self.connect()
        client.sendall(line)
        self.assertEqual(self.read_response(client), {
            "event": "UPLOAD_REJECTED", "request_id": "upload-2",
            "message": "Backend queue is full",
        })
        for number in range(10):
            self.assertEqual(self.pending.get_nowait(), {"queued_id": number})
            self.pending.task_done()
        client.sendall(line)
        self.assertEqual(self.read_response(client)["event"], "UPLOAD_ACCEPTED")
        self.assertEqual(self.pending.get(timeout=3), event)
        self.pending.task_done()

    def assert_event_queued(self):
        self.assertEqual(self.pending.get(timeout=3), EVENT)
        self.pending.task_done()
        self.assertTrue(self.pending.empty())

    def test_valid_event_once(self):
        self.connect().sendall(LINE)
        self.assert_event_queued()

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
            self.assertTrue(self.pending.empty())
            received.clear()
            client.sendall(LINE[10:-1])
            self.assertTrue(received.wait(3))
            self.assertTrue(self.pending.empty())
            client.sendall(b"\n")
            self.assert_event_queued()

    def test_bad_then_valid_same_connection(self):
        self.connect().sendall(b"bad-json\n" + LINE)
        self.assert_event_queued()
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
        self.assert_event_queued()

    def test_partial_disconnect(self):
        client = self.connect()
        client.sendall(LINE[:10])
        client.close()
        self.assertTrue(self.capture.wait_for(
            lambda messages: any("Discarded incomplete message: size=10" in message for message in messages)
        ))
        self.connect().sendall(LINE)
        self.assert_event_queued()

    def test_listener_enqueues_without_calling_processor(self):
        with patch("processor.process_resume_and_internship", side_effect=AssertionError("Unexpected processor call")) as handler:
            self.connect().sendall(LINE)
            self.assert_event_queued()
            handler.assert_not_called()

    def test_invalid_events_never_enter_queue(self):
        invalid = json.dumps({"resume": EVENT["resume"]}).encode() + b"\n"
        self.connect().sendall(invalid)
        self.assertTrue(self.capture.wait_for(
            lambda messages: any("internship must be a nonempty object" in message for message in messages)
        ))
        self.assertTrue(self.pending.empty())

    def test_full_queue_drops_then_recovers(self):
        existing = [{"queued_id": number} for number in range(10)]
        for event in existing:
            self.pending.put_nowait(event)
        client = self.connect()
        client.sendall(LINE)
        self.assertTrue(self.capture.wait_for(
            lambda messages: any("Event dropped: queue_size=10" in message for message in messages)
        ))
        self.assertEqual(self.pending.qsize(), 10)
        for expected in existing:
            self.assertIs(self.pending.get_nowait(), expected)
            self.pending.task_done()
        self.assertTrue(self.pending.empty())
        client.sendall(LINE)
        self.assert_event_queued()

    def test_close_clients_closes_and_untracks_handler(self):
        client = self.connect()
        self.assertTrue(self.capture.wait_for(
            lambda messages: any("Client connected" in message for message in messages)
        ))
        self.assertEqual(tcp_listener.close_clients(self.server, 3), 0)
        self.assertEqual(client.recv(1), b"")
        with self.server.clients_lock:
            self.assertEqual(self.server.active_clients, set())
            self.assertEqual(self.server.handler_threads, set())

    def test_close_clients_partial_warning_is_size_only(self):
        client = self.connect()
        received = threading.Event()
        original = tcp_listener.MessageBuffer.feed

        def observed_feed(buffer, data):
            result = original(buffer, data)
            received.set()
            return result

        partial = EVENT["resume"]["text"].encode()
        with patch.object(tcp_listener.MessageBuffer, "feed", observed_feed):
            client.sendall(partial)
            self.assertTrue(received.wait(3))
            self.assertEqual(tcp_listener.close_clients(self.server, 3), 0)
        warnings = [message for message in self.capture.messages if "incomplete message" in message]
        self.assertEqual(warnings, [f"Discarded incomplete message: size={len(partial)}"])
        self.assert_private(self.capture.messages)


if __name__ == "__main__":
    unittest.main()
