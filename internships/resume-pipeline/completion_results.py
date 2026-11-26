"""Process-local result queue helper.

The backend sends completed resumes directly to the writer queue as RESUME_WRITE.
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
