"""Shared resume object enriched by successive processing stages."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Education:
    school: str | None = None
    degree: str | None = None
    year: str | None = None


@dataclass
class Project:
    name: str | None = None
    date: str | None = None
    skills: list[str] = field(default_factory=list)


@dataclass
class Experience:
    title: str | None = None
    date: str | None = None
    duration_months: int | None = None
    duration: str | None = None


@dataclass
class Skills:
    languages: list[str] = field(default_factory=list)
    libraries: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    other: list[str] = field(default_factory=list)

    def all(self) -> list[str]:
        return self.languages + self.libraries + self.tools + self.other


@dataclass
class Resume:
    raw_text: str
    education: list[Education] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    skills: Skills = field(default_factory=Skills)
    experience: list[Experience] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize at JSON or storage boundaries, outside the event pipeline."""
        return asdict(self)
