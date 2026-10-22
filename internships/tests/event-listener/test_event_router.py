import os
import unittest
from pathlib import Path
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "event-listener"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from support import BaseTest

with patch.dict(os.environ, {"LOG_LEVEL": "INFO", "LOG_FILE": ""}):
    from event_router import EventRouter


class EventRouterTests(BaseTest):
    def test_routes_original_event_to_matching_handler_only(self):
        router = EventRouter()
        upload = Mock()
        other = Mock()
        router.register("RESUME_UPLOAD", upload)
        router.register("OTHER", other)
        event = {"event": "RESUME_UPLOAD", "data": {"discord_id": "123"}}
        router.route(event)
        upload.assert_called_once_with(event)
        self.assertIs(upload.call_args.args[0], event)
        other.assert_not_called()

    def test_unknown_or_missing_event_type_is_ignored(self):
        router = EventRouter()
        handler = Mock()
        router.register("RESUME_UPLOAD", handler)
        for event in ({"event": "UNKNOWN"}, {}):
            with self.subTest(event=event):
                router.route(event)
        handler.assert_not_called()
        self.assertEqual(self.output.getvalue().count("No handler registered for event:"), 2)

    def test_noncallable_registration_rejected(self):
        router = EventRouter()
        with self.assertRaises(TypeError):
            router.register("RESUME_UPLOAD", None)

    def test_registering_existing_type_replaces_handler(self):
        router = EventRouter()
        old = Mock()
        new = Mock()
        router.register("RESUME_UPLOAD", old)
        router.register("RESUME_UPLOAD", new)
        event = {"event": "RESUME_UPLOAD"}
        router.route(event)
        old.assert_not_called()
        new.assert_called_once_with(event)


if __name__ == "__main__":
    unittest.main()
