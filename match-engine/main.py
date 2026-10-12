import os
import signal
import sys
import threading

from log_config import get_logger


def main() -> None:
    # Configure logging on the main thread before importing server modules.
    try:
        logger = get_logger("main")
    except OSError:
        print("ERROR: Cannot open LOG_FILE", file=sys.stderr)
        sys.exit(2)

    # Import application modules only after logging is configured.
    from event_queue import create_queue, HandlerRegistry, Worker, stop_workers
    from processor import process_resume_and_internship
    from tcp_listener import create_server

    host = os.environ.get("TCP_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("TCP_PORT", "9000"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        logger.error("TCP_PORT must be an integer between 1 and 65535")
        sys.exit(2)

    try:
        max_size = int(os.environ.get("QUEUE_MAX_SIZE", "1000"))
        if max_size <= 0:
            raise ValueError
    except ValueError:
        logger.error("QUEUE_MAX_SIZE must be a positive integer")
        sys.exit(2)

    event_queue = create_queue(max_size)
    registry = HandlerRegistry()

    def process_event(event: dict) -> None:
        process_resume_and_internship(event["resume"], event["internship"])

    registry.register(process_event)
    worker = Worker(event_queue, registry)
    server = None
    stopping = threading.Event()

    def request_shutdown(signum=None, frame=None):
        if not stopping.is_set():
            logger.info("Shutdown requested")
            stopping.set()
            if server is not None:
                threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    worker.start()
    try:
        for attempt in range(1, 6):
            if stopping.is_set():
                return
            try:
                server = create_server(host, port, event_queue)
                break
            except OSError:
                logger.warning("Bind failed: host=%s port=%s attempt=%s/5", host, port, attempt)
                if attempt == 5:
                    logger.error("Unable to bind server after 5 attempts")
                    sys.exit(1)
                if stopping.wait(5):
                    return

        if not stopping.is_set():
            logger.info(
                "Server started: host=%s port=%s queue_max_size=%s",
                host, port, max_size,
            )
            server.serve_forever()
    except KeyboardInterrupt:
        request_shutdown()
    finally:
        if server is not None:
            server.server_close()
        alive = stop_workers(event_queue, [worker], timeout=30)
        if alive:
            logger.warning("Worker shutdown timed out: alive=%s", alive)


if __name__ == "__main__":
    main()
