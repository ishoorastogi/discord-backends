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

`main.py` is the central command in a single Python process. It creates a bounded
queue, registers handlers, starts one worker, and runs the TCP listener. The
listener only validates events and puts them on the queue. The worker gives every
event to every registered handler, in registration order. Currently, the only
handler is the processor, which logs IDs and sizes. Python 3.10 or newer is
required; all dependencies are in the standard library.

## Files

- `main.py`: central coordination of configuration, queue, handlers, worker, listener, bind retries, and shutdown.
- `tcp_listener.py`: message framing, validation, threaded TCP server, enqueueing, and active-client shutdown.
- `processor.py`: resume and internship processing function, called through the registered adapter; currently logs receipt only.
- `event_queue.py`: bounded queue helper, handler registry, worker, drain and stop helpers.
- `log_config.py`: shared console logging and optional file logging.
- `test_tcp_listener.py`: standard-library tests for logging, validation, framing, privacy, and sockets.
- `test_event_queue.py`: tests for queues, handlers, workers, drain timeouts, privacy, and shutdown configuration.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `TCP_HOST` | `127.0.0.1` | Address on which the server listens. |
| `TCP_PORT` | `9000` | TCP port; must be an integer from 1 to 65535. |
| `LOG_LEVEL` | `INFO` | Logging level; invalid values fall back to INFO with a warning. |
| `LOG_FILE` | Unset | Optional log file path, relative to the working directory. Console logging stays enabled. |
| `QUEUE_MAX_SIZE` | `1000` | Maximum queued event count; must be a positive integer. |
| `SHUTDOWN_TIMEOUT_SECONDS` | `30` | Shutdown coordination time limit; must be a positive finite number, with floats allowed. |

The `.env` file is not loaded automatically. Set environment variables in your
shell or pass them with the command. `.env.example` lists example values.

Invalid `TCP_PORT`, `QUEUE_MAX_SIZE`, or `SHUTDOWN_TIMEOUT_SECONDS` values exit
with status 2 and no traceback. `main.py` reads those variables and `TCP_HOST`;
it configures logging first through `log_config.py`, which reads `LOG_LEVEL` and
`LOG_FILE`. An unavailable log file also exits with status 2.

## Queue and overload behavior

The queue is bounded by `QUEUE_MAX_SIZE`. When full, the new event is dropped
with a WARNING and existing events are kept. There are no acknowledgments or
retries, so dropped events are not recovered. Queue size counts events, not bytes;
the separate 1 MiB limit applies to each incoming message.

## Adding a handler

Register a function with `HandlerRegistry.register` before starting the worker.
Every handler receives every event dict, in registration order. A failing handler
is logged by name and exception type only; it does not stop other handlers or
later events. Handlers must not log event text.

For example, when wiring handlers in `main.py`:

```python
def count_event(event: dict) -> None:
    # Inspect the event without logging its text.
    metrics["received"] += 1

metrics = {"received": 0}
registry.register(process_event)
registry.register(count_event)
worker = Worker(event_queue, registry)
worker.start()
```

Here, `event_queue` and `registry` are the queue and registry created by the
coordinator, and `process_event` is its adapter to the processor.

## Running

Run from the repository root:

```sh
TCP_HOST=127.0.0.1 TCP_PORT=9000 python3 match-engine/main.py
```

Stop with Ctrl+C or SIGTERM. Bind failures are retried up to five attempts,
with five seconds between attempts. Invalid port, queue-size, or shutdown-timeout
configuration or an unavailable log file exits with status 2; exhausted bind
attempts exit with status 1.
Normal shutdown exits with status 0.

## Shutdown

On SIGTERM or SIGINT, the server stops accepting connections. Active client
connections are closed; unfinished messages are discarded with a size-only
warning. Queued and in-flight events are drained, the worker is stopped with a
sentinel, and the server is closed.

After the accept loop stops, client closure, draining, and worker stopping share
one deadline of `SHUTDOWN_TIMEOUT_SECONDS`. A `drain completed` INFO line reports
the remaining event count. If the limit expires with unfinished work, one WARNING
reports undelivered events and live worker and client-thread counts. The process
still exits with status 0. Events left unfinished at exit are not persisted.

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

Expected result: `Ran 44 tests` followed by `OK`.

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
