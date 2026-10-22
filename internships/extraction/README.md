# Resume extraction

Extract education, projects, skills, and experience from plain resume text.
This package owns the extraction logic, structured models, and extraction
errors. It uses the Python standard library and works independently of PDF
parsing.

```text
extraction/
├── __init__.py    # Public extraction API
├── exceptions.py  # Extraction errors
├── extractor.py   # Structured field extraction
└── models.py      # Education, Project, Skills, Experience, ResumeData
```

From this directory, install the package and its test dependencies:

```sh
python3 -m pip install -r requirements.txt
python3 -m pytest
```

Tests live in `../tests/extraction/`.

Use the extraction API with plain text:

```python
from extraction import extract_resume_data

data = extract_resume_data("SKILLS\nProgramming Languages: Python")
print(data.to_dict())
```

`ResumeExtractor.extract(raw_text)` returns the same `ResumeData` structure.
Both APIs reject empty input with `extraction.EmptyResumeTextError`. Extraction
returns a new result and does not mutate a parser object.

To combine the two stages, install both packages, then pass parsed text into
extraction:

```python
from pathlib import Path

from extraction import extract_resume_data
from resume_parser import parse_resume_pdf

resume = parse_resume_pdf(Path("../data/uploads/another-resume.pdf"))
data = extract_resume_data(resume.raw_text)
```

The manual script `../test-scripts/extract_resume.py` accepts a UTF-8 text file
or reads standard input and prints structured JSON. See the
[manual script instructions](../test-scripts/README.md).
