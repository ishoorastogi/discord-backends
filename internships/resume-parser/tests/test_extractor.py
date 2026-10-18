from resume_parser import (
    ResumeExtractor,
    extract_resume_data,
    parse_resume_text,
)


def test_extract_resume_sections_and_multiple_entries():
    raw_text = """\
EDUCATION
University of Example | B.S. Computer Science | May 2024

PROJECTS
Forecast API | Python, FastAPI | Jan 2023 - Mar 2023
Technical: Python, FastAPI
Inventory Dashboard | React, PostgreSQL | Sep 2022 - Dec 2022

SKILLS
Programming Languages: Python, JavaScript
Libraries & Frameworks: FastAPI, React
Tools & Platforms: Docker, PostgreSQL

EXPERIENCE
Software Engineer | Example Co | Jan 2022 - Dec 2023
Data Intern | Sample Co | Jun 2021 - Aug 2021
"""

    resume = parse_resume_text(raw_text)
    data = extract_resume_data(resume.raw_text)

    assert len(data.education) == 1
    assert data.education[0].school == "University of Example"
    assert data.education[0].degree == "B.S. Computer Science"
    assert data.education[0].year == "2024"

    assert [project.name for project in data.projects] == [
        "Forecast API",
        "Inventory Dashboard",
    ]
    assert [project.date for project in data.projects] == [
        "Jan 2023 - Mar 2023",
        "Sep 2022 - Dec 2022",
    ]
    assert data.projects[0].skills == ["Python", "FastAPI"]
    assert data.projects[1].skills == ["React", "PostgreSQL"]

    assert data.skills.languages == ["Python", "JavaScript"]
    assert data.skills.libraries == ["FastAPI", "React"]
    assert data.skills.tools == ["Docker", "PostgreSQL"]

    assert [experience.title for experience in data.experience] == [
        "Software Engineer | Example Co",
        "Data Intern | Sample Co",
    ]
    assert [experience.duration_months for experience in data.experience] == [24, 3]
    assert [experience.duration for experience in data.experience] == [
        "2 yrs",
        "3 mos",
    ]


def test_resume_extractor_populates_and_returns_the_provided_resume():
    raw_text = """\
EDUCATION
University of Example | B.S. Computer Science | May 2024

SKILLS
Programming Languages: Python
"""
    resume = parse_resume_text("old resume text")

    result = ResumeExtractor.extract(resume, raw_text)

    assert result is resume
    assert resume.raw_text == raw_text.strip()
    assert resume.education[0].school == "University of Example"
    assert resume.skills.languages == ["Python"]
