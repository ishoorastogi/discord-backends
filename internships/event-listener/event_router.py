from shared.logs.log_config import get_logger

logger = get_logger("event_router")


class EventRouter:

    def __init__(self):
        self._handlers = {}

    def register(self, event_type: str, handler):

        if not callable(handler):
            raise TypeError("Handler must be callable")

        self._handlers[event_type] = handler

    def route(self, event: dict):

        event_type = event.get("event")

        handler = self._handlers.get(event_type)

        if handler is None:
            logger.warning(
                "No handler registered for event: %s",
                event_type
            )
            return

        handler(event)