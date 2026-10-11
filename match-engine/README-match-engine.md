**This is for match engine**

## Event schema

Events use UTF-8 newline-delimited JSON: one JSON object per line, terminated
by a newline. The maximum message size is 1 MiB (1,048,576 bytes), excluding
the terminating newline.

Each event requires two nonempty top-level objects, `resume` and `internship`:

- `resume` requires `id` and `text`. The `text` field contains extracted resume text.
- `internship` requires `id`.

All other fields are optional and subject to change.

Example event (send with a terminating newline):

```json
{"resume":{"id":"resume-123","text":"Python developer with SQL experience"},"internship":{"id":"internship-456","title":"Software Engineering Intern","description":"Python and SQL"}}
```

Newlines inside text must be JSON-escaped as `\n`, rather than literal newlines
that would split the event across lines.

## Overview

A single Python process listens on TCP, validates newline-delimited JSON events,
and hands each valid event directly to `process_resume_and_internship` in the
same process. Currently, the handler only logs IDs and sizes. Python 3.10 or
newer is required; all dependencies are in the standard library.

## Files

- `main.py`: configuration, startup, bind retries, and signal-based shutdown.
- `tcp_listener.py`: message framing, validation, threaded TCP server, and handoff.
- `processor.py`: the handoff function, currently logging receipt only.
- `log_config.py`: shared console logging and optional file logging.
- `test_tcp_listener.py`: standard-library tests for logging, validation, framing, privacy, and sockets.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `TCP_HOST` | `127.0.0.1` | Address on which the server listens. |
| `TCP_PORT` | `9000` | TCP port; must be an integer from 1 to 65535. |
| `LOG_LEVEL` | `INFO` | Logging level; invalid values fall back to INFO with a warning. |
| `LOG_FILE` | Unset | Optional log file path, relative to the working directory. Console logging stays enabled. |

The `.env` file is not loaded automatically. Set environment variables in your
shell or pass them with the command. `.env.example` lists example values.

## Running

Run from the repository root:

```sh
TCP_HOST=127.0.0.1 TCP_PORT=9000 python3 match-engine/main.py
```

Stop with Ctrl+C or SIGTERM. Bind failures are retried up to five attempts,
with five seconds between attempts. Invalid port configuration or an unavailable
log file exits with status 2; exhausted bind attempts exit with status 1.
Normal shutdown exits with status 0.

## Manual testing

With the server running, send an event from another terminal:

```sh
printf '%s\n' '{"resume":{"id":"resume-123","text":"Python developer with SQL experience"},"internship":{"id":"internship-456","title":"Software Engineering Intern","description":"Python and SQL"}}' | nc -w 1 127.0.0.1 9000
```

The server logs one processor INFO line containing the IDs `resume-123` and
`internship-456` and the sizes of the resume text and serialized internship.

Send malformed JSON, an event missing `internship`, then a valid event on the
same connection. The first two lines produce warnings; the valid event is still
processed:

```sh
printf '%s\n' 'bad-json' '{"resume":{"id":"r1","text":"Python"}}' '{"resume":{"id":"r1","text":"Python"},"internship":{"id":"i1","title":"Intern"}}' | nc -w 1 127.0.0.1 9000
```

This Python client sends half a line, pauses, then sends the remainder. No
processor receipt should appear before the final newline:

```sh
python3 -B -c 'import json, socket, time
line = json.dumps({"resume":{"id":"r1","text":"Python"},"internship":{"id":"i1","title":"Intern"}}).encode("utf-8") + b"\n"
with socket.create_connection(("127.0.0.1", 9000)) as client:
    midpoint = len(line) // 2
    client.sendall(line[:midpoint])
    time.sleep(1)
    client.sendall(line[midpoint:])'
```

## Running tests

From the repository root:

```sh
python3 -B -m unittest discover -s match-engine -p "test_*.py" -v
```

## Behavior and limits

- Each message is limited to 1 MiB, excluding its terminating newline. An oversized message closes that connection.
- Bad lines are discarded and logged; later valid lines on the connection can still be processed.
- An unfinished message is discarded with a size-only warning when its client disconnects.
- Events have no acknowledgments, retries, or persistence.
- The server listens on loopback only by default, for clients on the same machine.
- **Binding to a non-loopback address exposes a service with no access control.**

## Privacy

Event logs contain only IDs and sizes, never resume text or internship text or
descriptions. Operational logs also include client addresses, startup and shutdown
messages, and error reasons.
