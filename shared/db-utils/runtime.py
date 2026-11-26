"""Run async database operations from a dedicated synchronous thread."""

import asyncio
from contextlib import closing
import threading

from .crud import Connection


class DatabaseRuntime:
    """Own an event loop and close its database pools when the worker exits."""

    def __init__(self):
        self._lock = threading.Lock()
        self._loop = None
        self._owner = None
        self._closed = False

    def start(self) -> None:
        """Create the loop on the calling thread without opening any connections."""
        with self._lock:
            if self._closed:
                raise RuntimeError("Database runtime is closed")
            if self._loop is not None:
                self._require_owner()
                return
            self._loop = asyncio.new_event_loop()
            self._owner = threading.current_thread()

    def run(self, coroutine):
        """Execute a coroutine on the owning thread and return its result."""
        # Take ownership of the coroutine even if it cannot be scheduled.
        with closing(coroutine):
            with self._lock:
                if self._closed:
                    raise RuntimeError("Database runtime is closed")
                loop = self._loop
                if loop is None:
                    raise RuntimeError("Database runtime has not been started")
                self._require_owner()
            return loop.run_until_complete(coroutine)

    def close(self) -> None:
        """Close the pools on their loop, then shut down the loop permanently."""
        with self._lock:
            if self._closed:
                return
            loop = self._loop
            if loop is not None:
                self._require_owner()
                try:
                    asyncio.get_running_loop()
                except RuntimeError:
                    pass
                else:
                    raise RuntimeError("Database runtime cannot close inside a running event loop")
            self._closed = True

        if loop is not None:
            try:
                loop.run_until_complete(Connection.close_pool())
            finally:
                loop.close()

    def _require_owner(self) -> None:
        if threading.current_thread() is not self._owner:
            raise RuntimeError("Database runtime can only be used by its owning thread")
