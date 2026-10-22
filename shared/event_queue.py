import queue
import threading
import time

from shared.logs.log_config import get_logger


logger = get_logger("event_queue")
SENTINEL = object()


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


class Worker:
    def __init__(self, event_queue, registry):
        self._queue = event_queue
        self._registry = registry
        self._thread = threading.Thread(
            target=self._run, name="event-worker", daemon=True
        )

    def start(self):
        self._thread.start()

    def join(self, timeout=None) -> bool:
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _run(self):
        while True:
            event = self._queue.get()
            try:
                if event is SENTINEL:
                    return
                for handler in self._registry.handlers():
                    try:
                        handler(event)
                    except Exception as error:
                        logger.warning(
                            "Handler failed: handler=%s exception_type=%s",
                            getattr(handler, "__name__", type(handler).__name__),
                            type(error).__name__,
                        )
            finally:
                self._queue.task_done()


def drain(event_queue, timeout: float) -> int:
    deadline = time.monotonic() + timeout
    with event_queue.all_tasks_done:
        while event_queue.unfinished_tasks:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            event_queue.all_tasks_done.wait(remaining)
        return event_queue.unfinished_tasks


def stop_workers(event_queue, workers, timeout: float) -> int:
    deadline = time.monotonic() + timeout
    for worker in workers:
        try:
            event_queue.put(SENTINEL, timeout=max(0, deadline - time.monotonic()))
        except queue.Full:
            break
    alive = 0
    for worker in workers:
        if not worker.join(max(0, deadline - time.monotonic())):
            alive += 1
    logger.info("workers stopped: stopped=%s alive=%s", len(workers) - alive, alive)
    return alive
