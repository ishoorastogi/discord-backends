"""Load and validate the sample internship records from their JSON file."""

import json
from pathlib import Path


SAMPLE_INTERNSHIPS_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "uploads"
    / "sample_internships.json"
)


def load_sample_internships(path: Path = SAMPLE_INTERNSHIPS_PATH) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as sample_file:
        records = json.load(sample_file)

    if not isinstance(records, list):
        raise ValueError(f"Expected a list of internships in {path}")
    if any(not isinstance(record, dict) for record in records):
        raise ValueError(f"Every internship in {path} must be a JSON object")

    return records
