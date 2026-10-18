from pathlib import Path
import signal
import sys
import threading
import time

# Make listener modules and shared utilities available when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent / "event-listener"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from shared.logs.log_config import get_logger


def main() -> None:
    # Load local configuration before any loggers or server modules are created.
    config.load_environment()

    # Configure logging on the main thread before importing server modules.
    try:
        logger = get_logger("main")
    except OSError:
        print("ERROR: Cannot open LOG_FILE", file=sys.stderr)
        sys.exit(2)

    # Import application modules only after logging is configured.
    from event_queue import create_queue, HandlerRegistry, Worker, drain, stop_workers
    from processor import process_resume_and_internship
    from event_router import EventRouter
    from tcp_listener import create_server, close_clients

    try:
        settings = config.load_settings()
    except ValueError as error:
        logger.error("%s", error)
        sys.exit(2)

    host = settings.host
    port = settings.port
    max_size = settings.queue_max_size
    shutdown_timeout = settings.shutdown_timeout

    event_queue = create_queue(max_size)
    router = EventRouter()
        # Initialize event queue, handler registry, and event router
    event_queue = create_queue(max_size)
    registry = HandlerRegistry()
    router = EventRouter()

    # Handle resume uploads
    def handle_resume_upload(event: dict) -> None:

        data = event.get("data")

        if not isinstance(data, dict):
            logger.warning("Invalid resume upload payload")
            return

        discord_id = data.get("discord_id")

        if not isinstance(discord_id, str) or not discord_id.isdigit():
            logger.warning("Invalid Discord ID in resume upload")
            return

        logger.info(
            "Resume upload received: discord_id=%s",
            discord_id
        )

        # TODO: Forward event to resume processing pipeline

    # Handle existing resume/internship events
    def handle_legacy_event(event: dict) -> None:

        process_resume_and_internship(
            event["resume"],
            event["internship"]
        )

    # Register supported event types
    router.register("RESUME_UPLOAD", handle_resume_upload)

    # Route incoming events
    def process_event(event: dict) -> None:

        if "event" in event:
            router.route(event)
        else:
            handle_legacy_event(event)

    # Register the router with the event queue worker
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
        for attempt in range(1, config.BIND_ATTEMPTS + 1):
            if stopping.is_set():
                return
            try:
                server = create_server(host, port, event_queue)
                break
            except OSError:
                logger.warning(
                    "Bind failed: host=%s port=%s attempt=%s/%s",
                    host, port, attempt, config.BIND_ATTEMPTS,
                )
                if attempt == config.BIND_ATTEMPTS:
                    logger.error("Unable to bind server after %s attempts", config.BIND_ATTEMPTS)
                    sys.exit(1)
                if stopping.wait(config.BIND_RETRY_DELAY_SECONDS):
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
        deadline = time.monotonic() + shutdown_timeout

        def remaining_time():
            return max(0, deadline - time.monotonic())

        try:
            clients_alive = close_clients(server, remaining_time()) if server else 0
            undelivered = drain(event_queue, remaining_time())
            logger.info("drain completed: remaining=%s", undelivered)
            workers_alive = stop_workers(event_queue, [worker], remaining_time())
            if undelivered or workers_alive or clients_alive:
                logger.warning(
                    "Shutdown timed out: undelivered=%s workers_alive=%s clients_alive=%s",
                    undelivered, workers_alive, clients_alive,
                )
        finally:
            if server is not None:
                server.server_close()


if __name__ == "__main__":
    main()
