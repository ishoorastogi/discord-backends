import io
import logging
import os
from pathlib import Path
import sys
import subprocess
import threading
import time
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


class WorkerTests(BaseTest):
    def setUp(self):
        super().setUp()
        self.pending = event_queue.create_queue(10)
        self.registry = event_queue.HandlerRegistry()
        self.workers = []
        self.release = threading.Event()
        self.addCleanup(self.cleanup_workers)

    def cleanup_workers(self):
        self.release.set()
        active = [worker for worker in self.workers if not worker.join(0)]
        if active:
            self.assertEqual(event_queue.stop_workers(self.pending, active, 3), 0)

    def start_worker(self):
        worker = event_queue.Worker(self.pending, self.registry)
        worker.start()
        self.workers.append(worker)
        return worker

    def wait_drained(self):
        drained = threading.Event()

        def join_queue():
            self.pending.join()
            drained.set()

        thread = threading.Thread(target=join_queue, daemon=True)
        thread.start()
        self.assertTrue(drained.wait(3), "queue.join() did not return")
        thread.join(timeout=3)

    def test_worker_fifo_once_per_event(self):
        calls = []
        self.registry.register(calls.append)
        worker = self.start_worker()
        events = [{"id": number} for number in range(3)]
        for event in events:
            self.assertTrue(event_queue.enqueue(self.pending, event))
        self.wait_drained()
        self.assertEqual(calls, events)
        for actual, expected in zip(calls, events):
            self.assertIs(actual, expected)
        self.assertTrue(worker._thread.daemon)
        self.assertEqual(worker._thread.name, "event-worker")

    def test_handlers_receive_every_event_in_order(self):
        calls = []
        self.registry.register(lambda event: calls.append(("first", event)))
        self.registry.register(lambda event: calls.append(("second", event)))
        self.start_worker()
        events = [{"id": 1}, {"id": 2}]
        for event in events:
            event_queue.enqueue(self.pending, event)
        self.wait_drained()
        self.assertEqual(calls, [
            ("first", events[0]), ("second", events[0]),
            ("first", events[1]), ("second", events[1]),
        ])

    def test_handler_failure_continues_and_marks_tasks_done(self):
        failed = []
        delivered = []

        def failing_handler(event):
            failed.append(event)
            raise RuntimeError("private failure message")

        self.registry.register(failing_handler)
        self.registry.register(delivered.append)
        worker = self.start_worker()
        events = [{"id": 1}, {"id": 2}]
        for event in events:
            event_queue.enqueue(self.pending, event)
        self.wait_drained()
        self.assertEqual(failed, events)
        self.assertEqual(delivered, events)
        self.assertFalse(worker.join(0))
        self.assertNotIn("private failure message", self.output.getvalue())

    def test_handler_warning_does_not_expose_exception_message(self):
        def sensitive_handler(event):
            raise ValueError("secret resume text")

        self.registry.register(sensitive_handler)
        self.start_worker()
        event_queue.enqueue(self.pending, {"text": "secret internship text"})
        self.wait_drained()
        output = self.output.getvalue()
        self.assertIn("WARNING event_queue", output)
        self.assertIn("handler=sensitive_handler exception_type=ValueError", output)
        self.assertNotIn("secret", output)
        self.assertNotIn("Traceback", output)

    def test_sentinel_stops_and_is_acknowledged(self):
        worker = self.start_worker()
        self.pending.put(event_queue.SENTINEL)
        self.assertTrue(worker.join(3))
        self.wait_drained()

    def test_stop_two_workers(self):
        self.start_worker()
        self.start_worker()
        self.assertEqual(event_queue.stop_workers(self.pending, self.workers, 3), 0)
        self.assertTrue(all(worker.join(0) for worker in self.workers))
        self.wait_drained()
        self.assertIn("workers stopped: stopped=2 alive=0", self.output.getvalue())

    def test_stop_timeout_for_blocked_handler(self):
        entered = threading.Event()

        def blocking_handler(event):
            entered.set()
            self.release.wait()

        self.registry.register(blocking_handler)
        worker = self.start_worker()
        event_queue.enqueue(self.pending, {})
        self.assertTrue(entered.wait(3))
        self.assertEqual(event_queue.stop_workers(self.pending, [worker], 0.05), 1)
        self.assertIn("workers stopped: stopped=0 alive=1", self.output.getvalue())
        self.release.set()
        self.assertTrue(worker.join(3))
        self.wait_drained()

    def test_stop_full_queue_respects_timeout(self):
        self.pending = event_queue.create_queue(1)
        entered = threading.Event()

        def blocking_handler(event):
            entered.set()
            self.release.wait()

        self.registry.register(blocking_handler)
        worker = self.start_worker()
        self.pending.put({"id": "active"})
        self.assertTrue(entered.wait(3))
        self.pending.put({"id": "queued"})
        started = time.monotonic()
        self.assertEqual(event_queue.stop_workers(self.pending, [worker], 0.05), 1)
        self.assertLess(time.monotonic() - started, 1)
        self.release.set()
        self.wait_drained()
        self.assertEqual(event_queue.stop_workers(self.pending, [worker], 3), 0)
        self.wait_drained()

    def test_drain_finishes_processed_events(self):
        calls = []
        self.registry.register(calls.append)
        events = [{"id": 1}, {"id": 2}]
        for event in events:
            self.pending.put(event)
        self.start_worker()
        self.assertEqual(event_queue.drain(self.pending, 3), 0)
        self.assertEqual(calls, events)

    def test_drain_timeout_counts_inflight_and_queued_events(self):
        entered = threading.Event()

        def blocking_handler(event):
            entered.set()
            self.release.wait()

        self.registry.register(blocking_handler)
        self.start_worker()
        self.pending.put({"id": "active"})
        self.assertTrue(entered.wait(3))
        self.pending.put({"id": "queued"})
        started = time.monotonic()
        self.assertEqual(event_queue.drain(self.pending, 0.05), 2)
        self.assertLess(time.monotonic() - started, 1)
        self.release.set()
        self.assertEqual(event_queue.drain(self.pending, 3), 0)


class ShutdownConfigTests(BaseTest):
    def test_invalid_shutdown_timeout(self):
        main_path = str(Path(__file__).resolve().parent / "main.py")
        for value in ("0", "abc", "-1", "nan", "inf"):
            with self.subTest(value=value):
                environment = dict(
                    os.environ, SHUTDOWN_TIMEOUT_SECONDS=value,
                    TCP_PORT="9000", QUEUE_MAX_SIZE="1000",
                )
                result = subprocess.run(
                    [sys.executable, "-B", main_path], env=environment,
                    capture_output=True, text=True, timeout=3,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("SHUTDOWN_TIMEOUT_SECONDS must be", result.stderr)
                self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
