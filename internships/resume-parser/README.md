# Resume Parser

A set of Python modules for reading resume PDFs into raw text. Like
`../event-listener/`, the implementation lives directly in this directory:

```text
resume-parser/
├── exceptions.py      # Parser errors
├── parser.py          # Text and PDF parsing
├── pdf_reader.py      # PDF text extraction
└── resume_parser.py   # Public API exports
```

Tests live in `../tests/resume_parser/`, and uploaded PDFs live in
`../data/uploads/`. Manual test scripts live in `../test-scripts/`.
Structured field extraction lives in [`../extraction/`](../extraction/README.md).
The shared `Resume` model lives in [`../models/`](../models/README.md).

## Setup

From the repository root, enter the parser directory, then create and activate
a virtual environment and install the package and its test dependencies:

```bash
cd internships/resume-parser
python -m venv .venv
```

On macOS and Linux:

```bash
source .venv/bin/activate
```

On Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Install the package:

```powershell
python -m pip install -r requirements.txt
```

If this package was previously installed, rerun the install command above in
the same Python environment to update its editable installation to the flat
module layout.

## Usage

After installing the package as described above, run the sample script from
this directory. It uses `SWE_Resume_Template.pdf` in this directory by default
(relative to this directory). Supply your own PDF if that local file is absent:

```powershell
python ../test-scripts/parse_resume.py
```

To parse a different PDF, pass its path:

```powershell
python ../test-scripts/parse_resume.py "../data/uploads/another-resume.pdf"
```

The script prints raw resume text. Resume data may contain
sensitive information, so avoid sharing terminal output or committing real
resumes.

You can also call the parser from Python:

```python
from pathlib import Path

from resume_parser import parse_resume_pdf

resume = parse_resume_pdf(Path("../data/uploads/another-resume.pdf"))
print(resume.raw_text)
```

`parser.py` reads PDF or text content into the shared `Resume(raw_text=...)`
object. Parsing fills only `raw_text`; education, projects, skills, and experience
start empty for later stages to populate. `resume_parser.py` continues to export
`Resume` and the parsing API. Parsing has no dependency on the extraction package.

Parser tests live in `../tests/resume_parser/`. Run them from this directory with:

```bash
python -m pytest
```

Do not commit uploaded resumes or real resumes used for testing; they contain
sensitive personal information.
