# Define a resume dataclass to hold resume contents


from dataclasses import dataclass


@dataclass
class Resume:

    raw_text: str
