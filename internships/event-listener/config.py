"""Event listener settings; private connection values belong in internships/.env."""

from dataclasses import dataclass
import math
import os
from pathlib import Path

from dotenv import load_dotenv


LOG_LEVEL = "INFO"
LOG_FILE = None
QUEUE_MAX_SIZE = 1000
SHUTDOWN_TIMEOUT_SECONDS = 30.0
BIND_ATTEMPTS = 5
BIND_RETRY_DELAY_SECONDS = 5
MAX_MESSAGE_BYTES = 1048576
RECV_BUFFER_SIZE = 65536


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    queue_max_size: int
    shutdown_timeout: float


def load_environment() -> None:
    """Load internships/.env for the listener, preserving environment variables."""
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    os.environ.setdefault("LOG_LEVEL", LOG_LEVEL)
    if LOG_FILE is not None:
        os.environ.setdefault("LOG_FILE", str(LOG_FILE))


def load_settings() -> Settings:
    """Validate connection values and resolve optional configuration overrides."""
    host = os.environ.get("TCP_HOST", "").strip()
    if not host:
        raise ValueError("TCP_HOST is required; set it in internships/.env or the environment")

    try:
        port = int(os.environ.get("TCP_PORT", ""))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise ValueError("TCP_PORT must be an integer between 1 and 65535") from None

    try:
        max_size = int(os.environ.get("QUEUE_MAX_SIZE", str(QUEUE_MAX_SIZE)))
        if max_size <= 0:
            raise ValueError
    except ValueError:
        raise ValueError("QUEUE_MAX_SIZE must be a positive integer") from None

    try:
        timeout = float(os.environ.get("SHUTDOWN_TIMEOUT_SECONDS", str(SHUTDOWN_TIMEOUT_SECONDS)))
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError
    except ValueError:
        raise ValueError("SHUTDOWN_TIMEOUT_SECONDS must be a positive finite number") from None

    return Settings(host, port, max_size, timeout)
