# Manual test scripts

Run these scripts to inspect backend behavior manually. Automated tests live in
`../tests/`.

## Read a database user

Install dependencies from the repository root:

```sh
python3 -m pip install -r requirements.txt
```

Set `DB_USER` and `DB_PASSWORD` in `internships/src/.env` to your PostgreSQL
credentials. Set `DB_HOST`, `DB_PORT`, and `DB_NAME` in `shared/db-utils/.env`.
All five settings are required and must match your running database.
Existing shell environment variables take precedence over these files.

Read the first user, or select one by Discord ID:

```sh
python3 internships/test-scripts/read_user.py
python3 internships/test-scripts/read_user.py 123456789012345678
```

The script resolves both `.env` files relative to its own location, opens a read-only
transaction, and prints the user as JSON. It exits with a nonzero status for
invalid settings, connection/query errors, or no matching user.

## Resume parsing

Install the shared models, parser, and extraction packages from the repository root:

```sh
python3 -m pip install -e ./internships/resume-pipeline/models -e ./internships/resume-pipeline/resume-parser -e ./internships/resume-pipeline/extraction
```

Parse a local resume PDF and print its raw text:

```sh
python3 internships/test-scripts/parse_resume.py /path/to/resume.pdf
```

Without a PDF argument, the script uses
`internships/data/uploads/SWE_Resume_Template.pdf`. The script resolves its
parser imports and default PDF relative to its own location, so it can run from
any working directory. Explicit relative PDF paths use the working directory.

Runtime dependencies are declared in `../resume-pipeline/resume-parser/pyproject.toml`.

## Structured extraction

Extract structured fields from a UTF-8 text file and print JSON:

```sh
python3 internships/test-scripts/extract_resume.py /path/to/resume.txt
```

Without a text-file argument, extraction reads standard input. Combine both
stages to parse a PDF and then extract structured fields:

```sh
python3 internships/test-scripts/parse_resume.py /path/to/resume.pdf | python3 internships/test-scripts/extract_resume.py
```

The extraction script creates a shared `Resume` from its input text, fills its
structured fields, and serializes the result to JSON. It requires no PDF library.
Its package metadata lives in `../resume-pipeline/extraction/pyproject.toml`.
