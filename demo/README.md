# Live resume pipeline demonstration

Run from the repository root, on `feature/addu-resume-integration`
(the original `feature/resume-pipeline-integration` branch is also supported):

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B demo/resume_pipeline_demo.py
```

The script returns 0 only when the TCP upload is accepted, all five stages run
exactly once in order, and the final vectors pass validation. A TCP acknowledgment
alone never makes the demo successful. The complete runtime report includes
extracted fields, normalized JSON, actual vector sections, dtype, shape, and norms.

## What runs

1. `synthetic_resume.txt` becomes a valid one-page PDF in a temporary directory.
2. The production `internships/src/main.py` entry point starts its real workers,
   registry, router, and TCP listener. A demo-only wrapper binds the real server to
   an available loopback port instead of the configured port; configuration files
   are not edited. This demo starts its own server; it does not need an existing
   backend process.
3. A TCP client sends newline-delimited JSON: `RESUME_UPLOAD`, a generated request
   ID, a fictitious numeric Discord ID, and the base64 PDF.
4. The existing pipeline queues `PARSE`, `EXTRACTION`, `NORMALIZATION`, and
   `VECTORIZATION`. The real parser reads the PDF, extraction enriches the shared
   Resume dataclass, the adapter uses `Resume.to_dict()`, and the existing
   normalizer and vectorizer process those results.
5. An in-memory wrapper around router dispatch records intermediate stage inputs/results. The
   PARSE result is captured from the next queued EXTRACTION event, because PARSE
   constructs a new event. The wrapper delegates to the real router; it neither
   calls handlers directly nor inserts events or results. It checks original
   Resume identity, request/Discord IDs, unchanged normalized data, finite
   nonzero 384-dimensional float32 unit embeddings, and exact stage order.
6. The client receives VECTORIZATION_COMPLETE from the production result queue,
   validates the full event, calls task_done(), then shuts down the
   service. Production cleanup drains the queues and stops workers. The PDF is
   removed automatically; vectors remain in memory. No database or writer runs.

## Dependencies and offline inference

The parser uses **pypdf**, not pdfplumber. Required environment modules are NumPy,
Sentence Transformers, PyTorch, pypdf, python-dotenv, the existing shared models,
and the parser/extraction packages. Install already-declared dependencies with:

```sh
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install \
  -e internships/resume-pipeline/models \
  -e 'internships/resume-pipeline/resume-parser[dev]' \
  -e 'internships/resume-pipeline/extraction[dev]'
```

For this demonstration, the missing dependency was installed with:

```sh
.venv/bin/python -m pip install 'sentence-transformers>=2.2'
```

Verified environment: Python 3.14, NumPy 2.5.5, Sentence Transformers 6.3.0,
PyTorch 2.15.0, pypdf 6.21.4, python-dotenv 1.2.4. `pip check` passed.

The default demo uses **real all-MiniLM-L6-v2 inference**, including its real
section text construction and averaging. It requires a complete local model
cache. This machine used cached snapshot
`c9745ed1d9f207416be6d2e6f8de32d1f16199bf`. The runner sets `HF_HUB_OFFLINE=1`
and `TRANSFORMERS_OFFLINE=1` before model imports. No model is downloaded and no
credentials are required. A Hugging Face offline warning can appear even when
loading succeeds from cache. Missing or incomplete model files produce a failed
report; there is no automatic mocked fallback.

Normalization is **dictionary-only** for a repeatable demonstration. The demo
disables the configured ESCO CSV path in memory. The current extractor leaves
experience bullets and the education `field` empty.

If real inference is unavailable, run this separate, explicitly labeled mode:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B demo/resume_pipeline_demo.py --mock-model
```

Only model encoding is mocked in that mode; PDF parsing, extraction,
normalization, vectorization section aggregation, TCP transport, and queues remain
real. Its output says `MOCKED embeddings; real MiniLM inference NOT VERIFIED`.
Do not present it as proof of real model inference.

Use `--timeout 300` to allow more time on a slower machine. The normal default is
180 seconds. The script requires local socket permission. No production files,
handlers, algorithms, queue implementations, model dataclasses, or configuration
files are edited. Instrumentation exists only in this demo process.

## Observed real-run results

The real run reported all six processing/transport checks as PASS, plus exact
stage ordering and metadata preservation. Extracted skills were Python, JS, SQL,
Flask, and Postgres; normalized skills were python, javascript, sql, flask, and
postgresql. It extracted BS in Computer Science, Backend Developer at Fictional
Systems, REST API, and Web Application. All six produced vector sections
(skills, titles, experience, projects, education, overall) had shape `(384,)`,
dtype `float32`, finite values, and norms printed as `1.000000`.

Regression command:

```sh
PYTHONDONTWRITEBYTECODE=1 LOG_FILE='' .venv/bin/python -B -m pytest -p no:cacheprovider \
  internships/tests/test_resume_pipeline_integration.py \
  internships/tests/resume_parser internships/tests/extraction internships/tests/models \
  internships/tests/event-listener/test_resume_handler.py shared/logs -q
```

The full existing internship suite has 30 previously verified baseline failures
in tests referencing `main.config`; this demo does not modify those tests or
production startup code to address them. Persistence and downstream result
responses are outside this demo's scope.

## Production completion contract

`completion_results.get_result_queue()` exposes the dedicated bounded process-local
queue to a future writer running in the same process. Production startup first
initializes it using `QUEUE_MAX_SIZE`; the first initialization fixes its capacity.
Writers should attach after startup and use the existing pipeline import paths.
The vectorization handler enqueues a `VECTORIZATION_COMPLETE` envelope retaining
all metadata and the same data dictionary, with `resume`, `normalized_resume`,
and `resume_vectors`. It never routes this completion back into processing.

A consumer takes an event with `get()`/`get_nowait()`, persists or otherwise
handles it, then calls `task_done()`. No default consumer discards events. The demo
is a real consumer of this queue; its observer is only for intermediate stages.
The queue holds strong references after later events are processed. It survives
processing-worker shutdown in the running process, but is **not durable** across
process exit or crashes. Shutdown intentionally does not drain/join this result
queue without a writer, so pending completions cannot hang shutdown. A future
writer must coordinate persistence before process exit and handle failures after
`get()` explicitly; `task_done()` is queue accounting, not a durable acknowledgment.

If full, the handler logs failed completion delivery with Discord/request IDs and
does not log successful delivery. It does not retry or persist that rejected event.
Capacity and consumer throughput must be planned before production deployment.

In `internships/src/config.json`, `ESCO_CSV` enables the semantic layer and
`ESCO_CACHE_DIR` gives the backend a writable directory for its skill vectors.
With a `null` or omitted cache directory, ESCO keeps skill vectors in memory.
The backend reports dataset, model, and cache failures as normalization failures.

Python 3.10 clean installation/inference: **NOT VERIFIED**, because no Python
3.10 interpreter was found in PATH or standard installation locations. The
verified Python 3.14 stack is listed above; some installed dependency versions
require newer Python. Pip may resolve older compatible releases on Python 3.10,
but that combination needs its own clean-environment test before deployment.
