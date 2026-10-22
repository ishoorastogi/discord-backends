# discord-backends
Backend Applications for discord bots

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
