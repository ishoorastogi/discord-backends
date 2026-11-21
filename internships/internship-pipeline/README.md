# Internship pipeline

This pipeline creates an `Internship` object for each `applicationUrl` in
`internships/data/uploads/sample_internships.json`, fetches each page, and stores
its visible text in `raw_string`. The extractor then fills fields on that same
object using recognized labels and section headings. Fields with no matching
information keep their existing values.

Install the page-fetching dependencies from the repository root:

```sh
python -m pip install -r internships/internship-pipeline/requirements.txt
```

Run it from the repository root:

```sh
python internships/internship-pipeline/scripts/run_pipeline.py
```

The report at `internships/internship-pipeline/data/test_data/internship_results.txt`
is cleared at the start of every run and rewritten with each application URL
along with the extracted fields and raw page text. Request failures are recorded and do not stop the other
URLs from being processed. Models are in `models/`, reusable pipeline functions
are in `scripts/`, and tests are in `test_scripts/`.
