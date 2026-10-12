import json
import socket
import socketserver
import threading
import time

from log_config import get_logger
from event_queue import enqueue


logger = get_logger("tcp_listener")
MAX_MESSAGE_BYTES = 1048576


class MessageTooLargeError(Exception):
    pass


def validate_event(event: dict) -> str | None:
    resume = event.get("resume")
    internship = event.get("internship")
    if not isinstance(resume, dict) or not resume:
        return "resume must be a nonempty object"
    if not isinstance(internship, dict) or not internship:
        return "internship must be a nonempty object"
    if "id" not in resume:
        return "resume id is required"
    if "text" not in resume or not isinstance(resume["text"], str):
        return "resume text must be a string"
    if "id" not in internship:
        return "internship id is required"
    return None


class MessageBuffer:
    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[dict]:
        self._buffer.extend(data)
        events = []
        while True:
            newline = self._buffer.find(b"\n")
            if newline == -1:
                if len(self._buffer) > MAX_MESSAGE_BYTES:
                    raise MessageTooLargeError("Incomplete message exceeds size limit")
                return events
            if newline > MAX_MESSAGE_BYTES:
                raise MessageTooLargeError("Complete message exceeds size limit")
            line = bytes(self._buffer[:newline])
            del self._buffer[:newline + 1]
            if not line:
                continue
            try:
                text = line.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning("Discarded message: invalid UTF-8")
                continue
            try:
                event = json.loads(text)
            except (ValueError, RecursionError):
                logger.warning("Discarded message: invalid JSON")
                continue
            if not isinstance(event, dict):
                logger.warning("Discarded message: expected a JSON object")
                continue
            reason = validate_event(event)
            if reason is not None:
                logger.warning("Discarded message: %s", reason)
                continue
            events.append(event)

    def close(self) -> None:
        if self._buffer:
            logger.warning(
                "Discarded incomplete message: size=%s", len(self._buffer)
            )
            self._buffer.clear()


class EventHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        buffer = MessageBuffer()
        logger.info("Client connected: %s", self.client_address)
        try:
            while True:
                data = self.request.recv(65536)
                if not data:
                    break
                for event in buffer.feed(data):
                    enqueue(self.server.event_queue, event)
        except MessageTooLargeError:
            logger.warning("Closing client connection: message exceeds size limit")
        except (ConnectionError, OSError) as error:
            logger.warning("Client socket error: %s", type(error).__name__)
        finally:
            buffer.close()
            logger.info("Client disconnected: %s", self.client_address)


class EventServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, *args, **kwargs):
        self.clients_lock = threading.Lock()
        self.active_clients = set()
        self.handler_threads = set()
        self.closing_clients = False
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        thread = threading.Thread(
            target=self.process_request_thread,
            args=(request, client_address),
            daemon=self.daemon_threads,
        )
        with self.clients_lock:
            if self.closing_clients:
                self.shutdown_request(request)
                return
            self.active_clients.add(request)
            self.handler_threads.add(thread)
            try:
                thread.start()
            except Exception:
                self.active_clients.discard(request)
                self.handler_threads.discard(thread)
                raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            with self.clients_lock:
                self.active_clients.discard(request)
                self.handler_threads.discard(threading.current_thread())


def close_clients(server, timeout: float) -> int:
    deadline = time.monotonic() + timeout
    with server.clients_lock:
        server.closing_clients = True
        clients = list(server.active_clients)
        threads = list(server.handler_threads)
    for client in clients:
        try:
            client.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        client.close()
    for thread in threads:
        thread.join(max(0, deadline - time.monotonic()))
    return sum(thread.is_alive() for thread in threads)


def create_server(host: str, port: int, event_queue) -> socketserver.ThreadingTCPServer:
    server = EventServer((host, port), EventHandler)
    server.event_queue = event_queue
    return server
