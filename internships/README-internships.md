**This is for the internship bot backend**

`main.py` coordinates the backend. Its queue, processor, and TCP listener modules
live in `event-listener/`; listener tests live in `event-listener/tests/`. The entry point and
tests add `event-listener/` to Python's import path so these modules can be
imported by name.

Run from the repository root:

```sh
python3 -m pip install -r requirements.txt
# On a new checkout, copy internships/.env.example to internships/.env.
python3 internships/main.py
```

`event-listener/config.py` loads `internships/.env` before logging is configured. Keep private
connection values (`TCP_HOST` and `TCP_PORT`) in that `.env`, which Git ignores.
The service uses this file regardless of the working directory.

Edit `event-listener/config.py` for event listener defaults: logging level and optional log file,
queue capacity, shutdown timeout, bind retry count and delay, message size limit,
and receive buffer size. Logging, queue, and shutdown settings also accept
environment overrides. Shell values take precedence over `.env` values, which
take precedence over these defaults. Host and port have no code defaults.

Run the service tests from the repository root:

```sh
python3 -B -m unittest discover -s internships/event-listener/tests -p "test_*.py" -v
```
