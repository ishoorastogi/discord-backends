"""Regression coverage for shared resume state and boundary serialization."""

import json

from internships.models import Education, Experience, Project, Resume
from extraction import Resume as ExtractionResume
from resume_parser import Resume as ParserResume


def test_parser_exports_the_shared_model_and_defaults_are_independent():
    assert ParserResume is Resume
    assert ExtractionResume is Resume
    first = Resume(raw_text="First resume")
    second = Resume(raw_text="Second resume")

    first.education.append(Education(school="Example University"))
    first.projects.append(Project(name="Example project"))
    first.skills.languages.append("Python")
    first.experience.append(Experience(title="Engineer"))

    assert not second.education
    assert not second.projects
    assert not second.skills.languages
    assert not second.experience


def test_to_dict_serializes_raw_text_and_structured_fields_without_sharing_state():
    resume = Resume(raw_text="Resume content", education=[Education(school="Example University")])
    resume.skills.languages.append("Python")

    data = json.loads(json.dumps(resume.to_dict()))

    assert data["raw_text"] == "Resume content"
    assert data["education"][0]["school"] == "Example University"
    assert data["skills"]["languages"] == ["Python"]
    data["skills"]["languages"].append("Java")
    assert resume.skills.languages == ["Python"]
