"""Bounded, process-local handoff for VECTORIZATION_COMPLETE events.

A future writer calls get_result_queue(), then get()/get_nowait(), persists the
complete event, and calls task_done(). No automatic consumer discards results.
The first initialization fixes capacity for this process (production initializes
it from QUEUE_MAX_SIZE). Pending results survive processing-worker shutdown, but
not process exit. This queue is deliberately not included in processing drains:
without a writer, waiting for its unfinished tasks would hang shutdown.
"""
from threading import Lock

from shared.event_queue import create_queue

_result_queue = None
_lock = Lock()


def get_result_queue(max_size=1000):
    """Return the shared result queue; initialize once with a positive bound."""
    global _result_queue
    with _lock:
        if _result_queue is None:
            _result_queue = create_queue(max_size)
        return _result_queue
