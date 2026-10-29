"""Send a structured internship through a temporary backend instance.

Run: python3 internships/test-scripts/internship_upload.py [posting.json]
Without a file, uses test-data/internships.json (five postings). Stop any existing backend first.
Success verifies intake, parsing, and activation of the populate placeholder;
it does not assert database storage or completion of deferred stages.
"""

import argparse
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
from uuid import uuid4

from resume_upload import positive_timeout, wait_for_log

SERVICE_DIR = Path(__file__).resolve().parents[1]


DEFAULT_POSTINGS = Path(__file__).resolve().parent / "test-data/internships.json"


def run_test(internships, timeout):
    settings = json.loads((SERVICE_DIR / "src/config.json").read_text(encoding="utf-8"))
    host, port = settings["TCP_HOST"], settings["TCP_PORT"]
    client_host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
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
        for internship in internships:
            event = {
                "event": "INTERNSHIP_SUBMIT",
                "request_id": str(uuid4()),
                "data": {"internship": internship},
            }
            with socket.create_connection((client_host, port), timeout=timeout) as connection:
                connection.sendall((json.dumps(event) + "\n").encode("utf-8"))
            # Submit sequentially so each activation belongs to this posting.
            wait_for_log(process, output, "Internship submission queued for processing", timeout)
            wait_for_log(process, output, "Internship posting prepared for populate", timeout)
            wait_for_log(process, output, "Internship populate function activated", timeout)
            print(f"PASS: populate activated for internship {internship['id']}", flush=True)
        print(f"PASS: populate activated for all {len(internships)} internships", flush=True)
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("posting", nargs="?", type=Path, help="JSON object or array (default: test-data/internships.json)")
    parser.add_argument("--timeout", type=positive_timeout, default=15.0)
    args = parser.parse_args()
    try:
        payload = json.loads((args.posting or DEFAULT_POSTINGS).read_text(encoding="utf-8"))
        internships = payload if isinstance(payload, list) else [payload]
        if not internships or any(not isinstance(item, dict) for item in internships):
            raise ValueError("Posting JSON must contain an object or a nonempty array of objects")
        if any(not isinstance(item.get("id"), str) or not item["id"].strip() for item in internships):
            raise ValueError("Each internship must have a nonempty string id")
        run_test(internships, args.timeout)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
