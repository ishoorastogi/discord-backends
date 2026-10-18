import json
import logging
import os
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "event-listener"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from internships.tests.support import BaseTest, reset_logging


class StartupConfigTests(BaseTest):
    def setUp(self):
        super().setUp()
        reset_logging()
        from internships import main

        self.main = main
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        service_dir = self.root / "internships"
        service_dir.mkdir()
        self.env_path = service_dir / ".env"
        self.config_path = service_dir / "config.json"
        self.write_config()
        listener_dir = service_dir / "event-listener"
        listener_dir.mkdir()
        location = patch.object(main.config, "__file__", str(listener_dir / "config.py"))
        location.start()
        self.addCleanup(location.stop)
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)

    def write_config(self, **values):
        connection = {"TCP_HOST": "127.0.0.1", "TCP_PORT": 8000}
        connection.update(values)
        self.config_path.write_text(json.dumps(connection))

    def run_config(self, contents):
        self.env_path.write_text(contents)
        with self.assertRaises(SystemExit) as result:
            self.main.main()
        self.assertEqual(result.exception.code, 2)
        return self.output.getvalue()

    def test_loads_service_env_before_logging(self):
        output = self.run_config(
            'LOG_LEVEL=DEBUG\nSHUTDOWN_TIMEOUT_SECONDS=0\n'
        )
        self.assertIn("SHUTDOWN_TIMEOUT_SECONDS must be", output)
        self.assertEqual(logging.getLogger("main").level, logging.DEBUG)

    def test_shell_values_override_env_file(self):
        os.environ["SHUTDOWN_TIMEOUT_SECONDS"] = "0"
        output = self.run_config("SHUTDOWN_TIMEOUT_SECONDS=30\n")
        self.assertIn("SHUTDOWN_TIMEOUT_SECONDS must be", output)

    def test_missing_host_rejected(self):
        self.config_path.write_text('{"TCP_PORT": 8000}')
        output = self.run_config("")
        self.assertIn("TCP_HOST must be a nonempty string", output)

    def test_missing_port_rejected(self):
        self.config_path.write_text('{"TCP_HOST": "127.0.0.1"}')
        output = self.run_config("")
        self.assertIn("TCP_PORT must be an integer between 1 and 65535", output)

    def test_invalid_host_rejected(self):
        for host in (None, "", "   ", 123, []):
            with self.subTest(host=host):
                self.write_config(TCP_HOST=host)
                with self.assertRaisesRegex(ValueError, "TCP_HOST must be a nonempty string"):
                    self.main.config.load_settings()

    def test_invalid_port_rejected(self):
        for port in (None, 0, -1, 65536, "8000", "invalid", 8000.0, 8000.5, True, []):
            with self.subTest(port=port):
                self.write_config(TCP_PORT=port)
                with self.assertRaisesRegex(ValueError, "TCP_PORT must be an integer"):
                    self.main.config.load_settings()

    def test_port_boundaries_accepted(self):
        for port in (1, 65535):
            with self.subTest(port=port):
                self.write_config(TCP_PORT=port)
                self.assertEqual(self.main.config.load_settings().port, port)

    def test_invalid_queue_size_exits_without_traceback(self):
        for value in ("0", "-1", "abc", "1.5", ""):
            with self.subTest(value=value), patch.dict(os.environ, QUEUE_MAX_SIZE=value):
                output = self.run_config("")
                self.assertIn("QUEUE_MAX_SIZE must be a positive integer", output)
                self.assertNotIn("Traceback", output)

    def test_invalid_shutdown_timeout_exits_without_traceback(self):
        for value in ("0", "abc", "-1", "nan", "inf", ""):
            with self.subTest(value=value), patch.dict(os.environ, SHUTDOWN_TIMEOUT_SECONDS=value):
                output = self.run_config("")
                self.assertIn("SHUTDOWN_TIMEOUT_SECONDS must be a positive finite number", output)
                self.assertNotIn("Traceback", output)

    def test_loads_tcp_values_from_service_config(self):
        self.write_config(TCP_HOST=" 0.0.0.0 ", TCP_PORT=12345)
        settings = self.main.config.load_settings()
        self.assertEqual(settings.host, "0.0.0.0")
        self.assertEqual(settings.port, 12345)

    def test_tcp_environment_values_are_ignored(self):
        os.environ.update(TCP_HOST="wrong-host", TCP_PORT="invalid")
        self.env_path.write_text("TCP_HOST=another-host\nTCP_PORT=0\n")
        self.main.config.load_environment()
        settings = self.main.config.load_settings()
        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 8000)

    def test_missing_config_rejected_without_traceback(self):
        self.config_path.unlink()
        output = self.run_config("")
        self.assertIn("Cannot load internships/config.json", output)
        self.assertNotIn("Traceback", output)

    def test_invalid_json_rejected_without_traceback(self):
        for contents in ("", '{"TCP_HOST":', '{"TCP_PORT": 8000,}'):
            with self.subTest(contents=contents):
                self.config_path.write_text(contents)
                output = self.run_config("")
                self.assertIn("Cannot load internships/config.json", output)
                self.assertNotIn("Traceback", output)

    def test_unreadable_config_rejected(self):
        with patch.object(Path, "open", side_effect=PermissionError("Access denied")):
            with self.assertRaisesRegex(ValueError, "Cannot load internships/config.json"):
                self.main.config.load_settings()

    def test_non_object_config_rejected(self):
        for value in ([], None, True, 123, "settings"):
            with self.subTest(value=value):
                self.config_path.write_text(json.dumps(value))
                output = self.run_config("")
                self.assertIn("config.json must contain a JSON object", output)

    def test_does_not_load_working_directory_config(self):
        (self.root / "config.json").write_text('{"TCP_HOST": "wrong-host", "TCP_PORT": 1}')
        previous_directory = Path.cwd()
        try:
            os.chdir(self.root)
            settings = self.main.config.load_settings()
        finally:
            os.chdir(previous_directory)
        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.port, 8000)

    def test_shell_configuration_works_without_env_file(self):
        os.environ["SHUTDOWN_TIMEOUT_SECONDS"] = "0"
        with self.assertRaises(SystemExit) as result:
            self.main.main()
        self.assertEqual(result.exception.code, 2)
        self.assertIn("SHUTDOWN_TIMEOUT_SECONDS must be", self.output.getvalue())

    def test_does_not_load_repository_root_env(self):
        (self.root / ".env").write_text("QUEUE_MAX_SIZE=invalid\n")
        self.main.config.load_environment()
        settings = self.main.config.load_settings()
        self.assertEqual(settings.queue_max_size, self.main.config.QUEUE_MAX_SIZE)

    def test_uses_config_defaults(self):
        self.env_path.write_text("")
        log_file = str(self.root / "service.log")
        with patch.multiple(
            self.main.config, QUEUE_MAX_SIZE=25, SHUTDOWN_TIMEOUT_SECONDS=2.5,
            LOG_LEVEL="DEBUG", LOG_FILE=log_file,
        ):
            self.main.config.load_environment()
            settings = self.main.config.load_settings()
        self.assertEqual(settings.queue_max_size, 25)
        self.assertEqual(settings.shutdown_timeout, 2.5)
        self.assertEqual(os.environ["LOG_LEVEL"], "DEBUG")
        self.assertEqual(os.environ["LOG_FILE"], log_file)

    def test_environment_overrides_config_defaults(self):
        self.env_path.write_text("")
        os.environ.update(
            QUEUE_MAX_SIZE="12", SHUTDOWN_TIMEOUT_SECONDS="1.5",
            LOG_LEVEL="ERROR", LOG_FILE="",
        )
        with patch.multiple(self.main.config, LOG_LEVEL="DEBUG", LOG_FILE="service.log"):
            self.main.config.load_environment()
            settings = self.main.config.load_settings()
        self.assertEqual(settings.queue_max_size, 12)
        self.assertEqual(settings.shutdown_timeout, 1.5)
        self.assertEqual(os.environ["LOG_LEVEL"], "ERROR")
        self.assertEqual(os.environ["LOG_FILE"], "")


if __name__ == "__main__":
    unittest.main()
