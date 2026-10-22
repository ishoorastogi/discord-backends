from pathlib import Path

from resume_parser import pdf_reader


def test_extract_pdf_text_uses_layout_mode(monkeypatch):
    class FakePage:
        def extract_text(self, *, extraction_mode):
            assert extraction_mode == "layout"
            return "PyTorch"

    class FakeReader:
        def __init__(self, pdf_path):
            assert pdf_path == Path("sample.pdf")
            self.pages = [FakePage()]

    monkeypatch.setattr(pdf_reader, "PdfReader", FakeReader)

    assert pdf_reader.extract_pdf_text(Path("sample.pdf")) == "PyTorch"


def test_extract_pdf_text_from_bytes_uses_layout_mode(monkeypatch):
    class FakePage:
        def extract_text(self, *, extraction_mode):
            assert extraction_mode == "layout"
            return "PyTorch"

    class FakeReader:
        def __init__(self, pdf_stream):
            assert pdf_stream.getvalue() == b"pdf data"
            self.pages = [FakePage()]

    monkeypatch.setattr(pdf_reader, "PdfReader", FakeReader)

    assert pdf_reader.extract_pdf_text_from_bytes(b"pdf data") == "PyTorch"
