# discord-backends
Backend Applications for discord bots
I can type on here

The internship bot's resume parser is in
[`internships/resume-pipeline/resume-parser`](internships/resume-pipeline/resume-parser/README.md).
Structured field extraction is in
[`internships/resume-pipeline/extraction`](internships/resume-pipeline/extraction/README.md).

Run `./installer.sh` with Python 3.10 or newer installed. It creates a root
`.venv`, installs the backend and test packages, and caches the inference
models used by the resume pipeline. It enables model downloads for setup,
verifies the cache with networking disabled, and enables offline mode in
`internships/src/config.py` for backend startup. The ESCO dataset is verified as
`skills_en.csv` when configured. It also initializes `internships/src/.env` if
missing and prints setup links for dependencies that need manual steps.
Set `PYTHON_BIN` to select an interpreter when creating a new `.venv`.

```sh
./installer.sh
source .venv/bin/activate
python3 internships/src/main.py
```

## Python setup

From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python internships/main.py
```

Select `.venv/bin/python` as your editor's Python interpreter. The
`from dotenv import load_dotenv` import is provided by `python-dotenv` in
`requirements.txt`.

## Services

- [Match engine](match-engine/README-match-engine.md): TCP event listener for resume and internship data.
