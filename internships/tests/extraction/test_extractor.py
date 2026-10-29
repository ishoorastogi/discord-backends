import pytest

from extraction import (
    EmptyResumeTextError,
    ResumeExtractor,
    extract_resume_data,
)
from models import Resume


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

    resume = Resume(raw_text=raw_text)
    data = extract_resume_data(resume)

    assert data is resume
    assert resume.raw_text == raw_text

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


def test_resume_extractor_returns_structured_data():
    raw_text = """\
EDUCATION
University of Example | B.S. Computer Science | May 2024

SKILLS
Programming Languages: Python
"""
    resume = Resume(raw_text=raw_text)
    data = ResumeExtractor.extract(resume)

    assert data is resume
    assert data.education[0].school == "University of Example"
    assert data.skills.languages == ["Python"]


@pytest.mark.parametrize("extract", [extract_resume_data, ResumeExtractor.extract])
def test_extraction_rejects_empty_text(extract):
    resume = Resume(raw_text=" \n ")
    with pytest.raises(EmptyResumeTextError):
        extract(resume)
    assert not resume.education
    assert not resume.projects
    assert not resume.experience


def test_extracting_again_replaces_fields_on_the_same_resume():
    resume = Resume(raw_text="SKILLS\nProgramming Languages: Python")
    extract_resume_data(resume)
    assert resume.skills.languages == ["Python"]

    resume.raw_text = "SKILLS\nProgramming Languages: Java"
    result = extract_resume_data(resume)

    assert result is resume
    assert resume.skills.languages == ["Java"]
