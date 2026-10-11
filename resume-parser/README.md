# Resume Parser

A small Python package for extracting text from resume PDFs and representing
the result as a Python object.

## Setup

From this directory, create and activate a virtual environment, then install
the package and its test dependencies:

```bash
python -m venv .venv
```

On Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Install the package:

```powershell
python -m pip install -r requirements.txt
```

## Usage

After installing the package as described above, run the sample script from
this directory. It uses `data/uploads/test_resume_1.pdf` by default:

```powershell
python scripts/parse_resume.py
```

To parse a different PDF, pass its path:

```powershell
python scripts/parse_resume.py "data/uploads/another-resume.pdf"
```

The script prints the extracted text to the terminal. Resume data may contain
sensitive information, so avoid sharing terminal output or committing real
resumes.

You can also call the parser from Python:

```python
from pathlib import Path

from resume_parser import parse_resume_pdf

resume = parse_resume_pdf(Path("data/uploads/test_resume_1.pdf"))
print(resume.raw_text)
```

The initial scaffold extracts PDF text and stores it in a `Resume` object.
Extracting structured fields such as work experience and education can be
implemented in `parser.py`.

Run tests with:

```bash
pytest
```

Do not commit uploaded resumes or real resumes used for testing; they contain
sensitive personal information.
