# Resume Parser

A small Python package for extracting text from resume PDFs and representing
the result as a Python object.

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

If this package was previously installed from the repository's top-level
`resume-parser` directory, rerun the install command above in the same Python
environment to update its editable installation to the new location.

## Usage

After installing the package as described above, run the sample script from
this directory. It uses `../data/uploads/swe_resume_template.pdf` by default
(relative to this directory). Supply your own PDF if that local file is absent:

```powershell
python scripts/parse_resume.py
```

To parse a different PDF, pass its path:

```powershell
python scripts/parse_resume.py "../data/uploads/another-resume.pdf"
```

The script prints structured resume data as JSON. Resume data may contain
sensitive information, so avoid sharing terminal output or committing real
resumes.

You can also call the parser from Python:

```python
from pathlib import Path

from resume_parser import parse_resume_pdf

resume = parse_resume_pdf(Path("../data/uploads/another-resume.pdf"))
print(resume.raw_text)
```

The initial scaffold extracts PDF text and stores it in a `Resume` object.
Extracting structured fields such as work experience and education can be
implemented in `parser.py`.

Parser tests live in `../tests/resume_parser/`. Run them from this directory with:

```bash
python -m pytest
```

Do not commit uploaded resumes or real resumes used for testing; they contain
sensitive personal information.
