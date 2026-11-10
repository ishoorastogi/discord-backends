"""Create unpopulated internship objects from application URLs."""

from importlib import import_module

Internship = import_module("internships.internship-pipeline.models.Internship").Internship


def create_internship(record: dict[str, object]) -> Internship:
    application_url = record.get("applicationUrl")
    if not isinstance(application_url, str) or not application_url.strip():
        raise ValueError("Each sample internship must have a nonempty applicationUrl")

    return Internship(application_url=application_url.strip())


def create_internships(records: list[dict[str, object]]) -> list[Internship]:
    internships = []
    for index, record in enumerate(records, start=1):
        try:
            internships.append(create_internship(record))
        except ValueError as error:
            raise ValueError(f"Invalid sample internship at position {index}: {error}") from error
    return internships
