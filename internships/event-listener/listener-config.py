"""Backend settings; TCP connection values belong in internships/src/config.json."""

from dataclasses import dataclass
import json
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
MAX_MESSAGE_BYTES = 8388608
RECV_BUFFER_SIZE = 65536


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    queue_max_size: int
    shutdown_timeout: float


def load_environment() -> None:
    """Load internships/src/.env, preserving shell environment variables."""
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    os.environ.setdefault("LOG_LEVEL", LOG_LEVEL)
    if LOG_FILE is not None:
        os.environ.setdefault("LOG_FILE", str(LOG_FILE))


def load_settings() -> Settings:
    """Validate connection values and resolve optional configuration overrides."""
    config_path = Path(__file__).resolve().parent / "config.json"
    try:
        with config_path.open(encoding="utf-8") as config_file:
            connection = json.load(config_file)
    except (OSError, ValueError) as error:
        raise ValueError(f"Cannot load internships/src/config.json: {error}") from None
    if not isinstance(connection, dict):
        raise ValueError("internships/src/config.json must contain a JSON object")

    host = connection.get("TCP_HOST")
    if not isinstance(host, str) or not host.strip():
        raise ValueError("TCP_HOST must be a nonempty string in internships/src/config.json")
    host = host.strip()

    port = connection.get("TCP_PORT")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("TCP_PORT must be an integer between 1 and 65535 in internships/src/config.json")

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
