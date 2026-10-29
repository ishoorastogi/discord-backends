# Manual test scripts

Run these scripts to inspect backend behavior manually. Automated tests live in
`../tests/`.

## Resume parsing

Install the shared models, parser, and extraction packages from the repository root:

```sh
python3 -m pip install -e ./internships/models -e ./internships/resume-parser -e ./internships/extraction
```

Parse a local resume PDF and print its raw text:

```sh
python3 internships/test-scripts/parse_resume.py /path/to/resume.pdf
```

Without a PDF argument, the script uses
`internships/data/uploads/SWE_Resume_Template.pdf`. The script resolves its
parser imports and default PDF relative to its own location, so it can run from
any working directory. Explicit relative PDF paths use the working directory.

Runtime dependencies are declared in `../resume-parser/pyproject.toml`.

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
Its package metadata lives in `../extraction/pyproject.toml`.


## Internship upload

Stop any running backend, then run from the repository root:

```sh
.venv/bin/python internships/test-scripts/internship_upload.py
.venv/bin/python internships/test-scripts/internship_upload.py /path/to/posting.json
```

The optional JSON file contains an internship object or a nonempty array.
Without a file, the script uses the five supplied postings in
`test-data/internships.json`. Feed postings use `id`, `company`, `role`, and
`applicationUrl`; descriptions are not required for these postings. The original
`id`, `title`, `company`, `description`, and optional `url` format is also supported.
The script submits each posting sequentially and verifies populate activation for
each ID, then reports the total. No job URLs are fetched. The script starts the backend
using `src/config.json`, sends `INTERNSHIP_SUBMIT`, verifies intake and parse logs, then verifies the
`Internship populate function activated` logger message, and stops the process
it started. Use `--timeout 30` to
increase the per-stage timeout. There is no internship TCP acknowledgment;
acceptance is verified through logs from the isolated backend instance.

Extraction, normalization, vectorization, populate, and scrape remain TODOs.
The test verifies the submit → parse → populate flow and activation, not completed
processing or storage.
Populate and scrape event handlers are registered for future use and do not
advance events.
