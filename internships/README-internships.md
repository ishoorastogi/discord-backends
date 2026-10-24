**This is for the internship bot backend**

The [resume parser](resume-parser/README.md) reads PDF text, and
[extraction](extraction/README.md) turns plain text into structured fields.
Both use the shared [Resume model](models/README.md) in `models/`. Parsing creates
the object, and extraction fills its structured fields in place. Internal events
carry that same instance under `data.resume` through later stages.
From the repository root, run the installer with Python 3.10 or newer. It
installs all backend and test dependencies in `.venv` and creates `src/.env`
from its example if missing:

```bash
./installer.sh
source .venv/bin/activate
python -m pytest internships/tests/resume_parser internships/tests/extraction
```

Parser tests live in `tests/resume_parser/`, and extraction tests live in
`tests/extraction/`. Shared resume data lives in `data/`; uploaded PDFs in
`data/uploads/` are Git-ignored.

The parser and listener both keep their Python modules directly in their
respective directories. Manual test scripts live in `test-scripts/`. Run the
parser test script from the repository root with:

```sh
python3 internships/test-scripts/parse_resume.py /path/to/resume.pdf
```

That script prints raw text. To produce structured JSON, pipe its output into
the separate extraction script:

```sh
python3 internships/test-scripts/parse_resume.py /path/to/resume.pdf | python3 internships/test-scripts/extract_resume.py
```

`src/main.py` coordinates the backend. Its processor and TCP listener modules live
in `event-listener/`, and its event router and handlers live in `event-managers/`.
The queue and logging utilities live in `../shared/`. Service tests live in
`tests/event-listener/`. The entry point adds the listener, router, handler, and
shared directories to Python's import path so these modules can be imported by name.

After setup, run from the repository root:

```sh
source .venv/bin/activate
python3 internships/src/main.py
```

Set the TCP listener address in `internships/src/config.json`:

```json
{
  "TCP_HOST": "127.0.0.1",
  "TCP_PORT": 8000
}
```

`TCP_HOST` must be a nonempty string, and `TCP_PORT` must be a JSON integer from
1 to 65535. The service always reads these values from this file, regardless of
the working directory. Missing or invalid configuration exits with status 2.

`src/config.py` also loads `internships/src/.env` before logging is configured.
Use that Git-ignored file for optional logging, queue, and shutdown settings.

Edit `src/config.py` for event listener defaults: logging level and optional log file,
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

Run all internship tests from the repository root:

```sh
python3 -m pytest internships/tests
```

Shared logging tests remain in `shared/logs/`:

```sh
python3 -B -m unittest discover -s shared/logs -p "test_*.py" -v
```
