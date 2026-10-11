import json

from log_config import get_logger


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


import socketserver

from processor import process_resume_and_internship


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
                    try:
                        process_resume_and_internship(
                            event["resume"], event["internship"]
                        )
                    except Exception as error:
                        logger.exception(
                            "Processor failed: %s: %s", type(error).__name__, error
                        )
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


def create_server(host: str, port: int) -> socketserver.ThreadingTCPServer:
    return EventServer((host, port), EventHandler)
