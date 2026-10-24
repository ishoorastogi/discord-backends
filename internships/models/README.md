# Shared resume model

`internships.models.Resume` holds raw text together with education, projects,
skills, and experience. The supporting `Education`, `Project`, `Skills`, and
`Experience` classes are defined here as well.

Parsing creates one `Resume` and fills `raw_text`. Extraction fills the structured
fields on that same instance and returns it. Later stages receive that instance
through the event's `data.resume` field. Raw text stays available throughout.

```python
from resume_parser import parse_resume_text
from extraction import extract_resume_data

resume = parse_resume_text("SKILLS\nProgramming Languages: Python")
result = extract_resume_data(resume)
assert result is resume
```

`resume.to_dict()` creates a separate, serializable representation for JSON or
storage. Internal event queues carry the object itself.

The repository installer installs this package with the parser and extraction
packages. To install them manually from the repository root:

```sh
python3 -m pip install -e ./internships/models -e ./internships/resume-parser -e ./internships/extraction
```
