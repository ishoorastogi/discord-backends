"""Exceptions raised by resume parsing operations."""


class ResumeParserError(Exception):
    """Base exception for resume parser errors."""


class PdfReadError(ResumeParserError):
    """Raised when a PDF cannot be read or has no extractable text."""


class EmptyResumeTextError(ResumeParserError):
    """Raised when resume parsing receives empty text."""
