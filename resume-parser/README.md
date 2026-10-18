# Resume Parser

A small Python package for extracting text from resume PDFs and representing
the result as a Python object.

## Setup

From this directory, install the package and its test dependencies into your
current Python installation:

```powershell
python -m pip install -r requirements.txt
```

This installs dependencies into the selected Python installation, shared with
other projects using that installation.

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

PDF text extraction and `Resume` object creation are separate steps. To create
a `Resume` directly from text that has already been extracted:

```python
from resume_parser import ResumeFactory

resume = ResumeFactory().create_resume("Extracted resume text")
```

`ResumeFactory` handles creating the model from text; `parse_resume_pdf`
continues to coordinate PDF extraction and model creation.

Run tests with:

```bash
pytest
```

Do not commit uploaded resumes or real resumes used for testing; they contain
sensitive personal information.
