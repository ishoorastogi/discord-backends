import queue

from log_config import get_logger


logger = get_logger("event_queue")


def create_queue(max_size: int) -> queue.Queue:
    if max_size <= 0:
        raise ValueError("max_size must be positive")
    return queue.Queue(maxsize=max_size)


def enqueue(event_queue, event) -> bool:
    try:
        event_queue.put_nowait(event)
    except queue.Full:
        logger.warning("Event dropped: queue_size=%s", event_queue.qsize())
        return False
    return True


class HandlerRegistry:
    def __init__(self):
        self._handlers = []

    def register(self, handler):
        if not callable(handler):
            raise TypeError("handler must be callable")
        self._handlers.append(handler)

    def handlers(self):
        return self._handlers.copy()
