"""Send a structured internship through a temporary backend instance.

Run: python3 internships/test-scripts/internship_upload.py [posting.json]
Without a file, uses test-data/internships.json (five postings). Stop any existing backend first.
Success verifies intake, parsing, populate, scraping (if needed), and extraction;
it does not assert database storage or completion of deferred stages.
"""

import argparse
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import socket
import subprocess
import sys
import threading
import time
from uuid import uuid4

from resume_upload import positive_timeout, wait_for_log

SERVICE_DIR = Path(__file__).resolve().parents[1]


DEFAULT_POSTINGS = Path(__file__).resolve().parent / "test-data/internships.json"


def wait_for_stages(process, output, timeout, *, full_pipeline=False):
    """Workers may emit stage logs before their producer logs acceptance."""
    pending = {
        "Internship submission queued for processing",
        "Internship posting prepared for populate",
        "Internship populate function activated",
    }
    if full_pipeline:
        pending.update({"Handling INTERNSHIP_EXTRACTION event", "Handling INTERNSHIP_NORMALIZATION event"})
    deadline = time.monotonic() + timeout
    while pending:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError(f"Timed out waiting for backend stages: {sorted(pending)}")
        try:
            line = output.get(timeout=min(remaining, 0.1))
        except queue.Empty:
            if process.poll() is not None:
                raise RuntimeError(f"Backend exited with status {process.returncode}")
            continue
        if line is None:
            raise RuntimeError("Backend output closed before expected stages")
        if "Internship scraping failed:" in line:
            raise RuntimeError(line.strip())
        pending = {message for message in pending if message not in line}


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
        failures = []
        for internship in internships:
            event = {
                "event": "INTERNSHIP_SUBMIT",
                "request_id": str(uuid4()),
                "data": {"internship": internship},
            }
            with socket.create_connection((client_host, port), timeout=timeout) as connection:
                connection.sendall((json.dumps(event) + "\n").encode("utf-8"))
                with connection.makefile("rb") as responses:
                    line = responses.readline(65536)
                if not line.endswith(b"\n"):
                    raise RuntimeError("Incomplete internship upload acknowledgment")
                response = json.loads(line)
                if response.get("event") != "UPLOAD_ACCEPTED" or response.get("request_id") != event["request_id"]:
                    raise RuntimeError(f"Unexpected internship upload acknowledgment: {response}")
            print(f"PASS: upload acknowledged for internship {internship['id']}", flush=True)
            # Submit sequentially so each activation belongs to this posting.
            try:
                wait_for_stages(process, output, timeout, full_pipeline=True)
            except RuntimeError as error:
                failures.append(internship["id"])
                print(f"FAIL: internship {internship['id']}: {error}", flush=True)
                continue
            print(f"PASS: populate and extraction completed for internship {internship['id']}", flush=True)
        if failures:
            raise RuntimeError(f"Extraction failed for {len(failures)}/{len(internships)} internships: {', '.join(failures)}")
        print(f"PASS: populate and extraction completed for all {len(internships)} internships", flush=True)
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
    parser.add_argument("--timeout", type=positive_timeout, default=30.0)
    parser.add_argument("--fixture-html", type=Path, help="Serve this local HTML instead of fetching live job URLs")
    args = parser.parse_args()
    try:
        payload = json.loads((args.posting or DEFAULT_POSTINGS).read_text(encoding="utf-8"))
        internships = payload if isinstance(payload, list) else [payload]
        if not internships or any(not isinstance(item, dict) for item in internships):
            raise ValueError("Posting JSON must contain an object or a nonempty array of objects")
        if any(not isinstance(item.get("id"), str) or not item["id"].strip() for item in internships):
            raise ValueError("Each internship must have a nonempty string id")
        with ExitStack() as stack:
            if args.fixture_html:
                html = args.fixture_html.read_bytes()

                class FixtureHandler(BaseHTTPRequestHandler):
                    def do_GET(self):
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(html)

                    def log_message(self, *args):
                        pass

                server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
                stack.callback(server.server_close)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                stack.callback(thread.join, 3)
                stack.callback(server.shutdown)
                url = f"http://127.0.0.1:{server.server_port}/posting"
                internships = [
                    {**posting, "sourceApplicationUrl": posting.get("applicationUrl", posting.get("url")), "applicationUrl": url}
                    for posting in internships
                ]
                print("FIXTURE MODE: fetching local HTML instead of the original job URLs", flush=True)
            run_test(internships, args.timeout)
    except (OSError, ValueError, KeyError, RuntimeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
