# Resume extraction

Fill education, projects, skills, and experience on a shared `Resume` object.
This package owns the extraction logic and extraction errors. The models live
in [`../models/`](../models/README.md). Extraction uses the Python standard
library and works independently of PDF parsing.

```text
extraction/
├── __init__.py    # Public extraction API
├── exceptions.py  # Extraction errors
└── extractor.py   # Structured field extraction
```

From this directory, install the package and its test dependencies:

```sh
python3 -m pip install -r requirements.txt
python3 -m pytest
```

Tests live in `../tests/extraction/`.

Use the extraction API with a shared resume:

```python
from extraction import extract_resume_data
from internships.models import Resume

resume = Resume(raw_text="SKILLS\nProgramming Languages: Python")
result = extract_resume_data(resume)
assert result is resume
print(resume.skills.languages)
```

`ResumeExtractor.extract(resume)` also fills and returns the supplied object.
Both APIs reject empty text with `extraction.EmptyResumeTextError`. Extraction
preserves `raw_text` and replaces the structured fields when run again.

To combine the two stages, install both packages, then pass the parsed resume into
extraction:

```python
from pathlib import Path

from extraction import extract_resume_data
from resume_parser import parse_resume_pdf

resume = parse_resume_pdf(Path("../data/uploads/another-resume.pdf"))
extract_resume_data(resume)
print(resume.skills.languages)
```

The manual script `../test-scripts/extract_resume.py` accepts a UTF-8 text file
or reads standard input and prints structured JSON. See the
[manual script instructions](../test-scripts/README.md).
Within the event pipeline, stages pass the same object under `data.resume`.
Call `resume.to_dict()` only when serializing for JSON or storage.
