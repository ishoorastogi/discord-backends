import object_filler
from models import Resume


def test_fill_resume_from_pdf_uses_extracted_text_and_factory(monkeypatch):
    def extract_text(pdf_content):
        assert pdf_content == b"pdf data"
        return "  Extracted resume text  "

    monkeypatch.setattr(
        object_filler,
        "extract_pdf_text_from_bytes",
        extract_text,
    )

    class FakeFactory:
        def create_resume(self, text):
            assert text == "  Extracted resume text  "
            return Resume(raw_text=text.strip())

    monkeypatch.setattr(object_filler, "ResumeFactory", FakeFactory)

    resume = object_filler.fill_resume_from_pdf(b"pdf data")

    assert resume == Resume(raw_text="Extracted resume text")
