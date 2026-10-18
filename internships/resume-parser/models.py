"""Data model for parsed resume text."""

from dataclasses import dataclass


@dataclass
class Resume:
    raw_text: str
