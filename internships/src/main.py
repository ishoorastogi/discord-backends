from functools import partial
from importlib import import_module
from pathlib import Path
import signal
import sys
import threading
import time

# Make listener modules and shared utilities available when run directly.
SERVICE_DIR = Path(__file__).resolve().parent.parent
SHARED_DIR = SERVICE_DIR.parent / "shared"
for module_dir in (
    SERVICE_DIR / "event-listener",
    SERVICE_DIR.parent,
    SHARED_DIR,
    SHARED_DIR / "event-managers" / "router",
    SHARED_DIR / "event-managers" / "handler",
):
    sys.path.insert(0, str(module_dir))

listener_config = import_module("listener-config")
# The TCP listener imports the settings through the existing config module name.
sys.modules["config"] = listener_config
from shared.logs.log_config import get_logger


def main() -> None:
    # Load local configuration before any loggers or server modules are created.
    listener_config.load_environment()

    # Configure logging on the main thread before importing server modules.
    try:
        logger = get_logger("main")
    except OSError:
        print("ERROR: Cannot open LOG_FILE", file=sys.stderr)
        sys.exit(2)

    # Import application modules only after logging is configured.
    event_queue = import_module("event_queue")
    intake_handler = import_module("intake-handler")
    resume_handler = import_module("resume-handler")
    event_router = import_module("event_router")
    tcp_listener = import_module("tcp_listener")

    try:
        settings = listener_config.load_settings()
    except ValueError as error:
        logger.error("%s", error)
        sys.exit(2)

    host = settings.host
    port = settings.port
    max_size = settings.queue_max_size
    shutdown_timeout = settings.shutdown_timeout
    # Initialize event queue, handler registry, and event router
    intake_queue = event_queue.create_queue(max_size)
    resume_queue = event_queue.create_queue(max_size)

    registry = event_queue.HandlerRegistry()
    router = event_router.EventRouter()

    # Register supported event types
    router.register(
        "RESUME_UPLOAD",
        partial(intake_handler.handle_resume_upload, resume_queue=resume_queue),
    )
    router.register("PARSE", partial(resume_handler.handle_parse))

    # Register the router with the event queue worker
    registry.register(partial(intake_handler.process_event, router=router))
    worker = event_queue.Worker(intake_queue, registry)
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
        for attempt in range(1, listener_config.BIND_ATTEMPTS + 1):
            if stopping.is_set():
                return
            try:
                server = tcp_listener.create_server(host, port, intake_queue)
                break
            except OSError:
                logger.warning(
                    "Bind failed: host=%s port=%s attempt=%s/%s",
                    host, port, attempt, listener_config.BIND_ATTEMPTS,
                )
                if attempt == listener_config.BIND_ATTEMPTS:
                    logger.error("Unable to bind server after %s attempts", listener_config.BIND_ATTEMPTS)
                    sys.exit(1)
                if stopping.wait(listener_config.BIND_RETRY_DELAY_SECONDS):
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
            clients_alive = tcp_listener.close_clients(server, remaining_time()) if server else 0
            undelivered = event_queue.drain(intake_queue, remaining_time())
            logger.info("drain completed: remaining=%s", undelivered)
            workers_alive = event_queue.stop_workers(intake_queue, [worker], remaining_time())
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
