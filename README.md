# discord-backends
Backend Applications for discord bots
I can type on here

The internship bot's resume parser is in
[`internships/resume-parser`](internships/resume-parser/README.md).
Structured field extraction is in
[`internships/extraction`](internships/extraction/README.md).

Run `./installer.sh` with Python 3.10 or newer installed. It creates a root
`.venv`, installs the listener, parser, extraction, and test dependencies, and
initializes `internships/src/.env` if missing. Existing environment settings
are preserved. Set `PYTHON_BIN` to select a different Python interpreter.

```sh
./installer.sh
source .venv/bin/activate
python3 internships/src/main.py
```

## Services

- [Match engine](match-engine/README-match-engine.md): TCP event listener for resume and internship data.
