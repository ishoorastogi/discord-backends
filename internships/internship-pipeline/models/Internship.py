"""Define the internship data model used by the pipeline."""

from dataclasses import dataclass


@dataclass(slots=True)
class Internship:
    application_url: str
    job_id: str | None = None
    raw_string: str | None = None
    title: str | None = None
    company: str | None = None
    location: str | None = None
    employment_type: str | None = None
    workplace_type: str | None = None
    job_description: str | None = None
    required_skills: list[str] | None = None
    preferred_skills: list[str] | None = None
    qualifications: str | None = None
    responsibilities: str | None = None
    education_requirements: str | None = None
    experience_requirements: str | None = None
    benefits: str | None = None
    compensation: str | None = None
    date_posted: str | None = None
    scrape_error: str | None = None

    def __str__(self) -> str:
        fields = (
            ("Application URL", self.application_url),
            ("Job ID", self.job_id),
            ("Raw string", self.raw_string),
            ("Title", self.title),
            ("Company", self.company),
            ("Location", self.location),
            ("Employment type", self.employment_type),
            ("Workplace type", self.workplace_type),
            ("Job description", self.job_description),
            ("Required skills", self._format_list(self.required_skills)),
            ("Preferred skills", self._format_list(self.preferred_skills)),
            ("Qualifications", self.qualifications),
            ("Responsibilities", self.responsibilities),
            ("Education requirements", self.education_requirements),
            ("Experience requirements", self.experience_requirements),
            ("Benefits", self.benefits),
            ("Compensation", self.compensation),
            ("Date posted", self.date_posted),
            ("Scrape error", self.scrape_error),
        )
        return "\n".join(f"{name}: {value or 'Not provided'}" for name, value in fields)

    @staticmethod
    def _format_list(values: list[str] | None) -> str | None:
        return ", ".join(values) if values else None
