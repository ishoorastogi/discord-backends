"""Fill an internship's structured fields from its scraped posting text."""

import re

from importlib import import_module

Internship = import_module("internships.internship-pipeline.models.Internship").Internship


FIELD_LABELS = {
    "job_id": ("job id", "job requisition id", "requisition id", "job reference"),
    "title": ("title", "job title", "position title"),
    "company": ("company", "company name", "employer", "hiring organization"),
    "location": ("location", "locations", "job location"),
    "employment_type": ("employment type", "job type", "position type"),
    "workplace_type": ("workplace type", "work arrangement", "work model"),
    "job_description": ("description", "job description", "about the role", "role overview"),
    "required_skills": ("required skills", "technical skills", "must-have skills"),
    "preferred_skills": ("preferred skills", "nice-to-have skills", "desired skills"),
    "qualifications": ("qualifications", "requirements", "minimum qualifications",
                       "required qualifications", "preferred qualifications", "what we are looking for"),
    "responsibilities": ("responsibilities", "key responsibilities", "what you'll do", "what you will do"),
    "education_requirements": ("education", "education requirements"),
    "experience_requirements": ("experience", "experience requirements"),
    "benefits": ("benefits", "perks", "benefits and perks", "what you'll gain"),
    "compensation": ("compensation", "salary", "pay", "pay range", "salary range"),
    "date_posted": ("date posted", "posted date", "posting date"),
}
LABEL_TO_FIELD = {
    label: field for field, labels in FIELD_LABELS.items() for label in labels
}
OTHER_HEADINGS = {
    "about us", "about the company", "how to apply", "equal opportunity",
    "our culture", "who we are", "disclaimers", "what we offer",
}
SKILL_FIELDS = {"required_skills", "preferred_skills"}
SKILL_SEPARATOR = re.compile(r"[,;\n]|\s+\|\s+|[•●▪]")
BULLET_PREFIX = re.compile(r"^\s*[-*–—]\s+")


def extract_internship_data(internship: Internship) -> Internship:
    """Populate recognized fields, preserving source text and existing metadata."""
    if not internship.raw_string or not internship.raw_string.strip():
        return internship

    sections: dict[str, list[str]] = {}
    introduction: list[str] = []
    current: list[str] | None = introduction
    for raw_line in internship.raw_string.splitlines():
        line = raw_line.strip()
        label, _, value = line.strip("# ").partition(":")
        label = label.strip().casefold().replace("’", "'")
        if label in LABEL_TO_FIELD:
            current = sections.setdefault(LABEL_TO_FIELD[label], [])
            if value.strip():
                current.append(value.strip())
        elif label in OTHER_HEADINGS:
            current = None
        elif current is not None:
            current.append(line)

    # Visible-text fallback places a page's heading on its own first line.
    intro_lines = [line for line in introduction if line]
    if intro_lines:
        first_line = intro_lines[0]
        if (
            "title" not in sections
            and len(first_line) <= 150
            and re.search(r"\b(?:intern(?:ship)?|co[- ]?op)\b", first_line, re.IGNORECASE)
            and not first_line.endswith((".", "!", "?"))
        ):
            sections["title"] = [first_line]
            intro_lines = intro_lines[1:]
        if intro_lines:
            sections.setdefault("job_description", intro_lines)

    for field, lines in sections.items():
        value = "\n".join(lines).strip()
        if not value:
            continue
        if field in SKILL_FIELDS:
            skills = {}
            for item in SKILL_SEPARATOR.split(value):
                skill = BULLET_PREFIX.sub("", item).strip()
                if skill:
                    skills.setdefault(skill.casefold(), skill)
            if skills:
                setattr(internship, field, list(skills.values()))
        else:
            setattr(internship, field, value)
    return internship
