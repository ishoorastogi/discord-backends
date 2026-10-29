"""Extract structured data (education, projects, skills, experience) from resume text."""

from __future__ import annotations

import re
from datetime import date

from models import Education, Experience, Project, Resume, Skills

from .exceptions import EmptyResumeTextError


# --------------------------------------------------------------------------- #
# Regexes
# --------------------------------------------------------------------------- #

MONTH_RE = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?"
YEAR_RE = r"(?:19|20)\d{2}"
DATE_RE = rf"(?:{MONTH_RE}\s+)?{YEAR_RE}"
PRESENT_RE = r"(?:Present|Current|Now|Ongoing)"

RANGE_PATTERN = re.compile(
    rf"(?P<start>{DATE_RE})\s*(?:-|–|—|to)\s*(?P<end>{DATE_RE}|{PRESENT_RE})",
    re.IGNORECASE,
)
SINGLE_DATE_PATTERN = re.compile(DATE_RE, re.IGNORECASE)
YEAR_PATTERN = re.compile(YEAR_RE)

MONTHS = {
    m: i
    for i, m in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"],
        start=1,
    )
}

BULLET_PATTERN = re.compile(r"^\s*[•●▪■◦○·\-\*–—\uf0b7]\s*")

SECTION_ALIASES = {
    "education": r"education|academic background|academics",
    "projects": r"(?:personal |academic |selected |technical )?projects?",
    "skills": r"(?:technical )?skills(?: (?:&|and) \w+)?|technologies|tech stack",
    "experience": (
        r"(?:work |professional |relevant |industry )?experience"
        r"|employment(?: history)?|work history"
    ),
}
SECTION_PATTERNS = {
    name: re.compile(rf"^(?:{aliases})\s*:?$", re.IGNORECASE)
    for name, aliases in SECTION_ALIASES.items()
}
# Headings we don't extract, but which must end the previous section.
OTHER_HEADINGS = re.compile(
    r"^(?:summary|objective|profile|certifications?|awards?|honors?|publications?|"
    r"activities|leadership|extracurriculars?|volunteer(?:ing)?|interests|references|"
    r"coursework|relevant coursework)\s*:?$",
    re.IGNORECASE,
)

SCHOOL_PATTERN = re.compile(
    r"\b(?:University|College|Institute|Polytechnic|Academy|School)\b|\bUniv\.", re.IGNORECASE
)
DEGREE_PATTERN = re.compile(
    r"\b(?:Bachelor|Master|Doctor|Associate|B\.?\s?S\.?c?|B\.?\s?A\.?|B\.?\s?Eng|"
    r"M\.?\s?S\.?c?|M\.?\s?A\.?|M\.?\s?Eng|MBA|Ph\.?\s?D\.?)(?=[\s'’,.]|$)",
    re.IGNORECASE,
)
TECH_LABEL_PATTERN = re.compile(
    r"^\s*(?:technologies|technical(?: skills?)?|tech(?:nical)? stack|tools|built with|skills|stack)\s*:\s*(.+)$",
    re.IGNORECASE,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _split_sections(text: str) -> dict[str, list[str]]:
    """Group lines under their section heading."""
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        heading = line.strip("*_#: ").strip()
        matched = None
        if len(heading) <= 40:
            for name, pattern in SECTION_PATTERNS.items():
                if pattern.match(heading):
                    matched = name
                    break
            if matched is None and OTHER_HEADINGS.match(heading):
                current = None
                continue
        if matched:
            current = matched
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)
    return sections


def _find_date(text: str) -> str | None:
    """Return a date range (preferred) or single date found in text."""
    match = RANGE_PATTERN.search(text)
    if match:
        return match.group(0).strip()
    match = SINGLE_DATE_PATTERN.search(text)
    return match.group(0).strip() if match else None


def _strip_dates(text: str) -> str:
    text = RANGE_PATTERN.sub("", text)
    text = SINGLE_DATE_PATTERN.sub("", text)
    return text


def _clean(text: str) -> str:
    """Trim stray separators/whitespace left after removing other pieces."""
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" \t|,;:-–—•()[]")


def _to_year_month(token: str) -> tuple[int, int | None]:
    if re.fullmatch(PRESENT_RE, token.strip(), re.IGNORECASE):
        today = date.today()
        return today.year, today.month
    year = int(YEAR_PATTERN.search(token).group(0))
    month_match = re.search(MONTH_RE, token, re.IGNORECASE)
    month = MONTHS.get(month_match.group(0)[:3].lower()) if month_match else None
    return year, month


def _duration(date_text: str | None) -> tuple[int | None, str | None]:
    """Compute duration in months and a readable string from a date range."""
    if not date_text:
        return None, None
    match = RANGE_PATTERN.search(date_text)
    if not match:
        return None, None
    y1, m1 = _to_year_month(match.group("start"))
    y2, m2 = _to_year_month(match.group("end"))
    if m1 is None or m2 is None:
        months = (y2 - y1) * 12
    else:
        months = (y2 - y1) * 12 + (m2 - m1) + 1  # inclusive of both months
    months = max(months, 0)
    years, rem = divmod(months, 12)
    parts = []
    if years:
        parts.append(f"{years} yr{'s' if years != 1 else ''}")
    if rem or not parts:
        parts.append(f"{rem} mo{'s' if rem != 1 else ''}")
    return months, " ".join(parts)


def _split_entries(lines: list[str], start_pred=None) -> list[list[str]]:
    """Split a section's lines into entries.

    A new entry begins when:
      * a non-bullet line follows bullet lines (and looks like a header, not a
        wrapped continuation of the previous bullet), or
      * `start_pred(line)` is true and the current entry already has such a line.
    """
    entries: list[list[str]] = []
    current: list[str] = []
    prev_bullet = False
    has_start = False

    for line in lines:
        is_bullet = bool(BULLET_PATTERN.match(line))
        starts_new = False

        if current:
            if not is_bullet and prev_bullet:
                looks_like_header = bool(_find_date(line)) or line[0].isupper() and not line.endswith(".")
                starts_new = looks_like_header and not line[0].islower()
            if start_pred and start_pred(line) and has_start:
                starts_new = True

        if starts_new:
            entries.append(current)
            current, has_start = [], False

        current.append(line)
        prev_bullet = is_bullet
        if start_pred and start_pred(line):
            has_start = True

    if current:
        entries.append(current)
    return entries


def _split_items(value: str) -> list[str]:
    return [item for item in (_clean(i) for i in re.split(r"[,;|•·]", value)) if item]


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for item in items:
        key = item.lower()
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


# --------------------------------------------------------------------------- #
# Section extractors
# --------------------------------------------------------------------------- #


def extract_skills(lines: list[str]) -> Skills:
    skills = Skills()
    for line in lines:
        line = BULLET_PATTERN.sub("", line)
        if ":" in line:
            label, _, value = line.partition(":")
            label = label.lower()
            items = _split_items(value)
            if "language" in label:
                skills.languages += items
            elif "librar" in label or "framework" in label:
                skills.libraries += items
            elif any(k in label for k in ("tool", "platform", "database", "cloud", "technolog", "devops")):
                skills.tools += items
            else:
                skills.other += items
        else:
            skills.other += _split_items(line)

    skills.languages = _dedupe(skills.languages)
    skills.libraries = _dedupe(skills.libraries)
    skills.tools = _dedupe(skills.tools)
    skills.other = _dedupe(skills.other)
    return skills


def extract_education(lines: list[str]) -> list[Education]:
    results = []
    for entry in _split_entries(lines, start_pred=lambda l: bool(SCHOOL_PATTERN.search(l))):
        edu = Education()

        for line in entry:
            if edu.school is None and SCHOOL_PATTERN.search(line):
                edu.school = _clean(_strip_dates(line).split(",")[0] if "," in line else _strip_dates(line))
                # Handle "University of X | B.S. Computer Science" on one line
                edu.school = _clean(re.split(r"\s[|–—-]\s", edu.school)[0])
                break

        for line in entry:
            if DEGREE_PATTERN.search(line):
                degree = _strip_dates(line)
                if edu.school:
                    degree = degree.replace(edu.school, "")
                degree = re.sub(r"\b(?:GPA|Expected|Graduat\w*)\b.*", "", degree, flags=re.IGNORECASE)
                edu.degree = _clean(degree) or None
                break

        years = YEAR_PATTERN.findall(" ".join(entry))
        if years:
            edu.year = years[-1]  # last year in a range = graduation year

        if edu.school or edu.degree:
            results.append(edu)
    return results


def extract_experience(lines: list[str]) -> list[Experience]:
    results = []
    for entry in _split_entries(
        lines,
        start_pred=lambda line: not BULLET_PATTERN.match(line) and bool(_find_date(line)),
    ):
        header = [l for l in entry if not BULLET_PATTERN.match(l)]
        header_text = " | ".join(header)
        date_text = _find_date(header_text)
        months, duration_text = _duration(date_text)
        title = _clean(_strip_dates(header_text))
        if title or date_text:
            results.append(
                Experience(
                    title=title or None,
                    date=date_text,
                    duration_months=months,
                    duration=duration_text,
                )
            )
    return results


def _skills_mentioned(text: str, known_skills: list[str]) -> list[str]:
    found = []
    for skill in known_skills:
        pattern = rf"(?<![\w+#]){re.escape(skill)}(?![\w+#])"
        if re.search(pattern, text, re.IGNORECASE):
            found.append(skill)
    return found


def extract_projects(lines: list[str], known_skills: list[str]) -> list[Project]:
    results = []
    for entry in _split_entries(
        lines,
        start_pred=lambda line: not BULLET_PATTERN.match(line) and bool(_find_date(line)),
    ):
        header = [l for l in entry if not BULLET_PATTERN.match(l)]
        if not header:
            continue
        header_text = " | ".join(header)
        date_text = _find_date(header_text)

        # Name = first segment of the first header line, minus dates
        first = _clean(_strip_dates(header[0]))
        name = _clean(re.split(r"\s[|–—-]\s|\|", first)[0]) or None

        # 1) explicit "Technologies: ..." line
        skills: list[str] = []
        for line in entry:
            m = TECH_LABEL_PATTERN.match(BULLET_PATTERN.sub("", line))
            if m:
                skills += _split_items(m.group(1))

        # 2) "Name | Python, Flask | Jan 2024" style header segments
        if not skills:
            segments = [_clean(_strip_dates(s)) for s in re.split(r"\s*[|–—-]\s*", header_text)]
            segments = [s for s in segments if s and s != name]
            for seg in segments:
                if "," in seg:
                    skills += _split_items(seg)

        # 3) fall back to matching anything from the Skills section
        if not skills:
            skills = _skills_mentioned(" ".join(entry), known_skills)

        results.append(Project(name=name, date=date_text, skills=_dedupe(skills)))
    return results


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def extract_resume_data(resume: Resume) -> Resume:
    """Fill structured fields on a resume and return the same object."""
    text = resume.raw_text.strip()
    if not text:
        raise EmptyResumeTextError("Resume text cannot be empty.")
    sections = _split_sections(text)
    skills = extract_skills(sections.get("skills", []))
    education = extract_education(sections.get("education", []))
    projects = extract_projects(sections.get("projects", []), skills.all())
    experience = extract_experience(sections.get("experience", []))
    resume.education = education
    resume.projects = projects
    resume.skills = skills
    resume.experience = experience
    return resume


class ResumeExtractor:
    """Extract structured fields from resume text."""

    @staticmethod
    def extract(resume: Resume) -> Resume:
        """Fill structured fields on the supplied resume and return it."""
        return extract_resume_data(resume)
