"""Create Resume objects from extracted resume text."""

from resume_parser.exceptions import EmptyResumeTextError
from resume_parser.models import Resume


class ResumeFactory:
    """Build Resume objects independently of the input file format."""

    def create_resume(self, text: str) -> Resume:
        """Create a Resume from extracted text."""
        normalized_text = text.strip()
        if not normalized_text:
            raise EmptyResumeTextError("Resume text cannot be empty.")

        return Resume(raw_text=normalized_text)
