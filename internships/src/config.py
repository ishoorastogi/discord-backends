"""Backend settings from internships/src/config.json and the environment."""

from dataclasses import dataclass
import json
import logging
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
HF_HUB_OFFLINE = True
TRANSFORMERS_OFFLINE = True
MAX_MESSAGE_BYTES = 8388608
RECV_BUFFER_SIZE = 65536


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    queue_max_size: int
    shutdown_timeout: float
    esco_csv: Path | None = None
    esco_cache_dir: Path | None = None


def _rewrite_hub_offline_warning(record: logging.LogRecord) -> bool:
    message = record.getMessage()
    if message.startswith("Could not reach the Hub (") and "Using cached commit hash" in message:
        updated = message.replace(
            "To disable it, please unset the `HF_HUB_OFFLINE` environment variable.",
            "To disable it, set `HF_HUB_OFFLINE = False` in `internships/src/config.py`.",
        )
        if updated != message:
            record.msg = updated
            record.args = ()
    return True


def configure_ml_environment(*, offline: bool | None = None) -> None:
    hub_offline = HF_HUB_OFFLINE if offline is None else offline
    transformers_offline = TRANSFORMERS_OFFLINE if offline is None else offline
    os.environ["HF_HUB_OFFLINE"] = "1" if hub_offline else "0"
    os.environ["TRANSFORMERS_OFFLINE"] = "1" if transformers_offline else "0"
    logging.getLogger("huggingface_hub.hf_api").addFilter(_rewrite_hub_offline_warning)

def load_environment() -> None:
    """Load internships/src/.env, preserving shell environment variables."""
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    os.environ.setdefault("LOG_LEVEL", LOG_LEVEL)
    if LOG_FILE is not None:
        os.environ.setdefault("LOG_FILE", str(LOG_FILE))


def _optional_path(value: object, setting: str, directory: Path) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{setting} must be a string or null in internships/src/config.json")
    path = value.strip()
    return directory / path if path else None


def load_settings() -> Settings:
    """Validate service configuration and resolve optional environment overrides."""
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

    esco_csv = _optional_path(connection.get("ESCO_CSV"), "ESCO_CSV", config_path.parent)
    esco_cache_dir = _optional_path(connection.get("ESCO_CACHE_DIR"), "ESCO_CACHE_DIR", config_path.parent)

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

    return Settings(host, port, max_size, timeout, esco_csv=esco_csv, esco_cache_dir=esco_cache_dir)
