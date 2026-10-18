**This is for the internship bot backend**

The [resume parser](resume-parser/README.md) extracts resume PDF text and
structured data. From the repository root, install its runtime and test
dependencies and run its tests with:

```bash
cd internships/resume-parser
python -m pip install -r requirements.txt
python -m pytest
```

Parser tests live in `tests/resume_parser/`. Shared resume data lives in
`data/`; uploaded PDFs in `data/uploads/` are Git-ignored.

`main.py` coordinates the backend. Its queue, processor, and TCP listener modules
live in `event-listener/`; service tests live in `tests/event-listener/`. The entry point and
tests add `event-listener/` to Python's import path so these modules can be
imported by name.

Run from the repository root:

```sh
python3 -m pip install -r requirements.txt
# On a new checkout, copy internships/.env.example to internships/.env.
python3 internships/main.py
```

Set the TCP listener address in `internships/config.json`:

```json
{
  "TCP_HOST": "127.0.0.1",
  "TCP_PORT": 8000
}
```

`TCP_HOST` must be a nonempty string, and `TCP_PORT` must be a JSON integer from
1 to 65535. The service always reads these values from this file, regardless of
the working directory. Missing or invalid configuration exits with status 2.

`event-listener/config.py` also loads `internships/.env` before logging is configured.
Use that Git-ignored file for optional logging, queue, and shutdown settings.

Edit `event-listener/config.py` for event listener defaults: logging level and optional log file,
queue capacity, shutdown timeout, bind retry count and delay, message size limit,
and receive buffer size. Logging, queue, and shutdown settings also accept
environment overrides. Shell values take precedence over `.env` values, which
take precedence over these defaults. Host and port come only from `config.json`.

Run the service tests from the repository root:

```sh
python3 -B -m unittest discover -s internships/tests/event-listener -p "test_*.py" -v
```

The suite covers connection configuration, queues and workers, TCP message framing,
PING/PONG replies, upload acknowledgments, event routing, and startup/shutdown.
Configuration tests use temporary files rather than the service's local settings.
TCP integration tests bind to loopback on automatically assigned ports.

Run all internship tests, including the resume parser, from the repository root:

```sh
python3 -m pytest internships/tests
```

Shared logging tests remain in `shared/logs/`:

```sh
python3 -B -m unittest discover -s shared/logs -p "test_*.py" -v
```
