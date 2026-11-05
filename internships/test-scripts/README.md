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
The script submits each posting sequentially, verifies `UPLOAD_ACCEPTED` with
the matching request ID, then waits for extraction to reach normalization.
Acceptance confirms intake queue admission before payload validation. Both
`INTERNSHIP_SUBMIT` and `INTERNSHIP_UPLOAD` are supported.

The internship flow is submit → parse → populate → scrape (when no text is
supplied) → extraction → normalization. Populate creates the shared Internship
object and retains the source posting in `data.internship_posting`. Scraping
fetches the application URL using requests and BeautifulSoup, with a timeout and
response-size limit. Supplied `raw_string` or `description` skips scraping.
Extraction enriches the same object. Normalization and vectorization are still
placeholders; storage is not implemented.

Install dependencies using `./installer.sh`, or install the new scraper dependencies:

```sh
.venv/bin/python -m pip install -r internships/internship-pipeline/requirements.txt
```

Live pages can expire or block requests. The script reports failed IDs and exits
with a nonzero status if any posting fails. `--timeout 45` raises the per-posting
timeout. To exercise real HTTP fetching and extraction with a repeatable local
page for all five records:

```sh
.venv/bin/python internships/test-scripts/internship_upload.py --fixture-html internships/test-scripts/test-data/internship_posting.html
```

Fixture mode explicitly replaces submitted application URLs with a local HTTP
server URL and retains each original URL as `sourceApplicationUrl`. It does not
modify the source JSON file and does not test the live employers' websites.

Resume extraction remains registered under `EXTRACTION` and enriches the shared
Resume before normalization and vectorization. Internship events use prefixed
names so the two flows do not collide.
