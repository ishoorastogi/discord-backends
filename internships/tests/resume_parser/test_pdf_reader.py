from pathlib import Path

from resume_parser import pdf_reader


def test_extract_pdf_text_uses_layout_mode(monkeypatch):
    class FakePage:
        def extract_text(self, *, extraction_mode):
            assert extraction_mode == "layout"
            return "PyTorch"

    class FakeReader:
        def __init__(self, _pdf_path):
            self.pages = [FakePage()]

    monkeypatch.setattr(pdf_reader, "PdfReader", FakeReader)

    assert pdf_reader.extract_pdf_text(Path("sample.pdf")) == "PyTorch"
