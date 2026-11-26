import asyncio
from contextlib import ExitStack
from importlib import import_module
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, Mock, patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "event-listener"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from internships.src import main
from support import BaseTest

with patch.dict(os.environ, {"LOG_LEVEL": "INFO", "LOG_FILE": ""}):
    import processor
    import tcp_listener


class MainTests(BaseTest):
    def setUp(self):
        super().setUp()
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(main.config, "load_environment"))
        stack.enter_context(patch.object(
            main.config, "load_settings",
            return_value=main.config.Settings("127.0.0.1", 12345, 10, 3),
        ))
        stack.enter_context(patch.multiple(main.config, BIND_ATTEMPTS=3, BIND_RETRY_DELAY_SECONDS=0))
        self.signals = stack.enter_context(patch.object(main.signal, "signal"))
        self.server = Mock()
        self.create_server = stack.enter_context(patch.object(
            tcp_listener, "create_server", return_value=self.server,
        ))
        self.close_clients = stack.enter_context(patch.object(tcp_listener, "close_clients", return_value=0))
        self.process_legacy = stack.enter_context(patch.object(processor, "process_resume_and_internship"))

    def serve_events(self, *events):
        def serve():
            pending = self.create_server.call_args.args[2]
            for event in events:
                pending.put_nowait(event)
        self.server.serve_forever.side_effect = serve

    def test_legacy_events_processed_and_shutdown_drains_queue(self):
        event = {"resume": {"id": "r1", "text": "private"}, "internship": {"id": "i1"}}
        self.serve_events(event)
        main.main()
        self.process_legacy.assert_called_once_with(event["resume"], event["internship"])
        self.assertEqual(self.create_server.call_args.args[:2], ("127.0.0.1", 12345))
        pending = self.create_server.call_args.args[2]
        self.assertEqual(pending.maxsize, 10)
        self.assertEqual(pending.unfinished_tasks, 0)
        self.assertTrue(pending.empty())
        self.close_clients.assert_called_once()
        self.server.server_close.assert_called_once()
        self.assertIn("workers stopped: stopped=1 alive=0", self.output.getvalue())

    def test_resume_upload_routed_without_legacy_processing(self):
        self.serve_events({
            "event": "RESUME_UPLOAD", "data": {"discord_id": "12345", "text": "PRIVATE_RESUME_TEXT"},
        })
        main.main()
        self.process_legacy.assert_not_called()
        self.assertIn("Resume upload received: discord_id=12345", self.output.getvalue())
        self.assertNotIn("PRIVATE_RESUME_TEXT", self.output.getvalue())

    def test_writer_survives_database_failure_and_drains_its_queue(self):
        resume_handler = import_module("resume-handler")
        writer_handler = import_module("writer-handler")
        connection = import_module("shared.db-utils.crud.Connection")
        vectorizer = import_module("vectorization.resume_vectorizer")
        vector = np.zeros(384, dtype=np.float32)
        vector[0] = 1
        attempts = []
        commits = []
        pool_closed_on = []

        async def close_pool():
            pool_closed_on.append((threading.current_thread(), asyncio.get_running_loop()))

        async def commit(*exc):
            self.assertIsNone(exc[0])
            self.assertNotIn("Resume successfully written", self.output.getvalue())
            commits.append(True)

        transaction = AsyncMock()
        transaction.__aexit__.side_effect = commit
        conn = Mock(execute=AsyncMock(), fetch=AsyncMock(side_effect=[[{"user_id": 7}], [{"user_id": 7}]]))
        conn.transaction.return_value = transaction
        pool = Mock(close=AsyncMock(side_effect=close_pool))
        pool.acquire.return_value = AsyncMock()
        pool.acquire.return_value.__aenter__.return_value = conn

        async def open_pool(**settings):
            attempts.append((threading.current_thread(), asyncio.get_running_loop()))
            if len(attempts) == 1:
                raise ConnectionError("private database error")
            return pool

        create_pool = AsyncMock(side_effect=open_pool)

        def serve():
            create_pool.assert_not_called()
            pending = self.create_server.call_args.args[2]
            pending.put_nowait({
                "event": "RESUME_WRITE", "data": {
                    "discord_id": "100", "resume": resume_handler.Resume("sample", overall_vector=vector.tolist()),
                },
            })
            for discord_id in ("101", "102"):
                pending.put_nowait({
                    "event": "VECTORIZATION",
                    "data": {
                        "discord_id": discord_id,
                        "resume": resume_handler.Resume("sample"),
                        "normalized_resume": {},
                    },
                })

        self.server.serve_forever.side_effect = serve
        with (
            patch.object(writer_handler, "logger", main.get_logger("main")),
            patch.object(vectorizer, "vectorize_resume", return_value={"overall_vector": vector}),
            patch.object(connection, "_pool", None),
            patch.object(connection, "_pool_init_lock", None),
            patch.object(connection.asyncpg, "create_pool", create_pool),
        ):
            main.main()

        self.assertEqual(commits, [True])
        self.assertEqual(conn.fetch.await_args_list[0].args[1:], ("102",))
        writer_thread, loop = attempts[0]
        self.assertIsNot(writer_thread, threading.current_thread())
        self.assertEqual(attempts, [(writer_thread, loop), (writer_thread, loop)])
        self.assertEqual(pool_closed_on, [(writer_thread, loop)])
        self.assertTrue(loop.is_closed())
        self.assertIn("RESUME_WRITE transaction failed: discord_id=101 exception_type=ConnectionError", self.output.getvalue())
        self.assertEqual(self.output.getvalue().count("Resume successfully written for user_id=7"), 1)
        self.assertNotIn("private database error", self.output.getvalue())
        self.assertIn("drain completed: remaining=0", self.output.getvalue())
        self.assertIn("writer queue workers stopped: stopped=1 alive=0", self.output.getvalue())
        self.server.server_close.assert_called_once()

    def test_writer_registration_preserves_payload_validation(self):
        writer_handler = import_module("writer-handler")
        router = import_module("event_router").EventRouter()
        db_runtime = Mock()
        writer_handler.register_handlers(router, db_runtime=db_runtime)

        with patch.object(writer_handler, "logger") as logger:
            router.route({"event": "RESUME_WRITE", "data": []})
            logger.warning.assert_called_once_with("Invalid RESUME_WRITE payload")
            logger.reset_mock()
            router.route({"event": "RESUME_WRITE", "data": {"discord_id": 123}})
            logger.warning.assert_called_once_with("Invalid Discord ID in RESUME_WRITE payload")
            logger.reset_mock()
            router.route({"event": "RESUME_WRITE", "data": {"discord_id": "123"}})
            logger.warning.assert_called_once_with("Missing or invalid Resume in RESUME_WRITE payload")

        db_runtime.run.assert_not_called()

    def test_internship_submission_uses_worker_and_shutdown_drains_queue(self):
        self.serve_events({
            "event": "INTERNSHIP_SUBMIT",
            "request_id": "internship-test",
            "data": {"internship": {
                "id": "i1", "title": "Intern", "company": "Example",
                "description": "PRIVATE_INTERNSHIP_DESCRIPTION",
            }},
        })
        main.main()
        output = self.output.getvalue()
        self.assertIn("Internship submission queued for processing", output)
        self.assertIn("Internship posting prepared for populate", output)
        self.assertIn("Internship populate function activated", output)
        self.assertIn("Handling INTERNSHIP_EXTRACTION event", output)
        self.assertIn("Handling INTERNSHIP_NORMALIZATION event", output)
        self.assertIn("internship queue workers stopped: stopped=1 alive=0", output)
        self.assertIn("drain completed: remaining=0", output)
        self.assertNotIn("PRIVATE_INTERNSHIP_DESCRIPTION", output)
        self.process_legacy.assert_not_called()
        self.server.server_close.assert_called_once()

    def test_invalid_uploads_warn_and_worker_continues(self):
        invalid_payloads = [None, [], "private"]
        invalid_ids = [None, "", "abc", 123]
        events = [{"event": "RESUME_UPLOAD", "data": value} for value in invalid_payloads]
        events.extend({"event": "RESUME_UPLOAD", "data": {"discord_id": value}} for value in invalid_ids)
        events.append({"event": "RESUME_UPLOAD", "data": {"discord_id": "12345"}})
        self.serve_events(*events)
        main.main()
        output = self.output.getvalue()
        self.assertEqual(output.count("Invalid resume upload payload"), len(invalid_payloads))
        self.assertEqual(output.count("Invalid Discord ID in resume upload"), len(invalid_ids))
        self.assertIn("Resume upload received: discord_id=12345", output)
        self.assertNotIn("Handler failed", output)
        self.process_legacy.assert_not_called()

    def test_unknown_event_is_ignored_and_next_event_processed(self):
        event = {"resume": {"id": "r1", "text": "private"}, "internship": {"id": "i1"}}
        self.serve_events({"event": "UNKNOWN"}, event)
        main.main()
        self.assertIn("No handler registered for event: UNKNOWN", self.output.getvalue())
        self.process_legacy.assert_called_once_with(event["resume"], event["internship"])

    def test_failed_bind_retries_then_serves(self):
        self.create_server.side_effect = [OSError("busy"), self.server]
        main.main()
        self.assertEqual(self.create_server.call_count, 2)
        self.server.serve_forever.assert_called_once()
        self.server.server_close.assert_called_once()
        self.assertIn("Bind failed: host=127.0.0.1 port=12345 attempt=1/3", self.output.getvalue())

    def test_exhausted_bind_retries_stop_worker_and_exit_one(self):
        self.create_server.side_effect = OSError("busy")
        with self.assertRaises(SystemExit) as result:
            main.main()
        self.assertEqual(result.exception.code, 1)
        self.assertEqual(self.create_server.call_count, 3)
        self.server.serve_forever.assert_not_called()
        self.close_clients.assert_not_called()
        self.assertIn("workers stopped: stopped=1 alive=0", self.output.getvalue())

    def test_signal_shutdown_is_idempotent(self):
        shutdown_finished = threading.Event()
        self.server.shutdown.side_effect = shutdown_finished.set

        def receive_signals():
            callbacks = {call.args[0]: call.args[1] for call in self.signals.call_args_list}
            callbacks[signal.SIGTERM](signal.SIGTERM, None)
            callbacks[signal.SIGTERM](signal.SIGTERM, None)
            self.assertTrue(shutdown_finished.wait(3))

        self.server.serve_forever.side_effect = receive_signals
        main.main()
        self.server.shutdown.assert_called_once()
        self.server.server_close.assert_called_once()
        self.assertEqual(self.output.getvalue().count("Shutdown requested"), 1)

    def test_keyboard_interrupt_stops_server_and_worker(self):
        shutdown_finished = threading.Event()
        self.server.shutdown.side_effect = shutdown_finished.set
        self.server.serve_forever.side_effect = KeyboardInterrupt
        main.main()
        self.assertTrue(shutdown_finished.wait(3))
        self.server.server_close.assert_called_once()
        self.assertIn("workers stopped: stopped=1 alive=0", self.output.getvalue())

    def test_server_failure_still_cleans_up(self):
        self.server.serve_forever.side_effect = RuntimeError("server failed")
        with self.assertRaisesRegex(RuntimeError, "server failed"):
            main.main()
        self.close_clients.assert_called_once()
        self.server.server_close.assert_called_once()
        self.assertIn("workers stopped: stopped=1 alive=0", self.output.getvalue())

    def test_unfinished_clients_report_shutdown_timeout(self):
        self.close_clients.return_value = 1
        main.main()
        self.assertIn("Shutdown timed out: undelivered=0 workers_alive=0 clients_alive=1", self.output.getvalue())
        self.server.server_close.assert_called_once()


class EntryPointTests(unittest.TestCase):
    def test_cli_runs_from_unrelated_directory_with_isolated_config(self):
        service = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copied_service = root / "internships"
            copied_src = copied_service / "src"
            copied_src.mkdir(parents=True)
            for filename in ("main.py", "config.py", "__init__.py"):
                shutil.copy2(service / "src" / filename, copied_src / filename)
            shutil.copytree(service / "event-listener", copied_service / "event-listener")
            shutil.copytree(service / "event-managers", copied_service / "event-managers")
            shutil.copytree(service / "resume-pipeline", copied_service / "resume-pipeline")
            shutil.copytree(service / "internship-pipeline", copied_service / "internship-pipeline")
            shutil.copytree(service.parent / "shared", root / "shared")
            (copied_src / "config.json").write_text(json.dumps({"TCP_HOST": "127.0.0.1", "TCP_PORT": 12345}))
            unrelated = root / "unrelated"
            unrelated.mkdir()
            result = subprocess.run(
                [sys.executable, "-B", str(copied_src / "main.py")], cwd=unrelated,
                env={"QUEUE_MAX_SIZE": "0", "LOG_LEVEL": "INFO", "LOG_FILE": ""},
                capture_output=True, text=True, timeout=5,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("QUEUE_MAX_SIZE must be a positive integer", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
