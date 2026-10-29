"""Send an uploaded PDF through the real TCP listener and implemented handlers.

Run: python3 internships/test-scripts/resume_upload.py [resume.pdf]

The default resume is the newest PDF in internships/data/uploads. An optional
filename is resolved within that directory. The script starts src/main.py using
src/config.json, checks UPLOAD_ACCEPTED, waits for the NORMALIZATION handler's log,
and shuts down the backend it started. Stop any existing backend first.

NORMALIZATION is currently a placeholder; success confirms PDF parsing,
structured extraction, and delivery through that handler. Application startup
errors fail the test and are printed without changing application code.
"""

import argparse
import base64
import json
import math
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
from uuid import uuid4


SERVICE_DIR = Path(__file__).resolve().parents[1]
UPLOADS_DIR = SERVICE_DIR / "data" / "uploads"


def positive_timeout(value):
    seconds = float(value)
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("timeout must be a positive finite number")
    return seconds


def select_resume(filename):
    if filename:
        resume = (UPLOADS_DIR / filename).resolve()
        if not resume.is_relative_to(UPLOADS_DIR.resolve()):
            raise ValueError("Choose a resume inside internships/data/uploads")
    else:
        candidates = [
            path for path in UPLOADS_DIR.iterdir()
            if path.is_file() and path.suffix.lower() == ".pdf"
        ]
        if not candidates:
            raise ValueError("No resume PDFs found in internships/data/uploads")
        resume = max(candidates, key=lambda path: (path.stat().st_mtime_ns, path.name))
    if not resume.is_file() or resume.suffix.lower() != ".pdf":
        raise ValueError(f"Resume PDF not found: {resume}")
    return resume


def wait_for_log(process, output, message, timeout):
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(f"Timed out waiting for backend log: {message}")
        try:
            line = output.get(timeout=min(remaining, 0.1))
        except queue.Empty:
            if process.poll() is not None:
                raise RuntimeError(f"Backend exited with status {process.returncode}; see its output above")
            continue
        if line is None:
            raise RuntimeError("Backend output closed before the expected processing stage")
        if message in line:
            return


def run_test(resume, discord_id, timeout):
    settings = json.loads((SERVICE_DIR / "src" / "config.json").read_text(encoding="utf-8"))
    host = settings["TCP_HOST"]
    port = settings["TCP_PORT"]
    # Wildcard bind addresses need a concrete loopback destination for the client.
    client_host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
    pdf_bytes = resume.read_bytes()
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError(f"File does not have a PDF header: {resume}")

    request_id = str(uuid4())
    event = {
        "event": "RESUME_UPLOAD",
        "request_id": request_id,
        "data": {
            "discord_id": discord_id,
            "name": "Resume upload test",
            "filename": resume.name,
            "content_type": "application/pdf",
            "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        },
    }
    message = (json.dumps(event) + "\n").encode("utf-8")
    print(f"Resume: {resume.name} ({len(pdf_bytes)} bytes)", flush=True)
    print(f"Starting backend at {host}:{port}; request_id={request_id}", flush=True)
    environment = {
        **os.environ,
        "LOG_LEVEL": "INFO",
        "LOG_FILE": "",
        "PYTHONUNBUFFERED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    process = subprocess.Popen(
        [sys.executable, "-B", str(SERVICE_DIR / "src" / "main.py")],
        cwd=SERVICE_DIR.parent,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = queue.Queue()

    def collect_output():
        for line in process.stdout:
            print(line, end="", flush=True)
            output.put(line)
        output.put(None)

    reader = threading.Thread(target=collect_output, daemon=True)
    reader.start()
    try:
        wait_for_log(process, output, "Server started:", timeout)
        with socket.create_connection((client_host, port), timeout=timeout) as connection:
            connection.sendall(message)
            with connection.makefile("rb") as response_stream:
                response_line = response_stream.readline(65536)
            if not response_line.endswith(b"\n"):
                raise RuntimeError("Listener did not return a complete upload acknowledgment")
            response = json.loads(response_line)
            if response.get("event") != "UPLOAD_ACCEPTED" or response.get("request_id") != request_id:
                raise RuntimeError(f"Unexpected upload acknowledgment: {response}")
        print("PASS: listener acknowledged RESUME_UPLOAD", flush=True)

        # Logs can arrive before the TCP acknowledgment; the queue preserves them.
        wait_for_log(process, output, f"Resume upload received: discord_id={discord_id}", timeout)
        wait_for_log(process, output, f"Resume parsing successful for discord ID {discord_id}", timeout)
        wait_for_log(process, output, "Handling EXTRACTION event", timeout)
        wait_for_log(process, output, f"Moving to NORMALIZATION stage: discord_id={discord_id}", timeout)
        wait_for_log(process, output, "Handling NORMALIZATION event", timeout)
        print("PASS: RESUME_UPLOAD → PARSE → EXTRACTION → NORMALIZATION", flush=True)
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        reader.join(timeout=timeout)
        process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("resume", nargs="?", help="PDF filename inside internships/data/uploads (default: newest PDF)")
    parser.add_argument("--discord-id", default="123456789012345678", help="Numeric Discord ID for the test event")
    parser.add_argument("--timeout", type=positive_timeout, default=15.0, help="Timeout per stage in seconds (default: 15)")
    args = parser.parse_args()
    if not args.discord_id.isascii() or not args.discord_id.isdigit():
        parser.error("--discord-id must contain only digits")
    try:
        run_test(select_resume(args.resume), args.discord_id, args.timeout)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Test interrupted", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
