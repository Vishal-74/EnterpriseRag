"""Extract text from PDF, TXT, Markdown, and CSV uploads."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.core.errors import ParseError
from app.domain import DocumentKind

_BLANK_LINES = re.compile(r"\n{4,}")


@dataclass(frozen=True)
class ParsedDocument:
    kind: DocumentKind
    text: str
    pages: list[str] | None = None


def preprocess(text: str) -> str:
    """Normalize newlines without changing the words."""
    cleaned = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    return _BLANK_LINES.sub("\n\n\n", cleaned).strip()


def parse_document(kind: DocumentKind, data: bytes) -> ParsedDocument:
    """Parse bytes into text and, for PDFs, per-page text."""
    if kind == "pdf":
        return _parse_pdf(data)
    text = _decode(data)
    parsed = preprocess(text)
    if not parsed:
        raise ParseError("No text could be extracted from the file.")
    return ParsedDocument(kind=kind, text=parsed)


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return data.decode("cp1252")
        except UnicodeDecodeError as exc:
            raise ParseError("The file encoding is not supported.") from exc


def _parse_pdf(data: bytes) -> ParsedDocument:
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ParseError("Encrypted PDFs are not supported.")
        pages = [preprocess(page.extract_text() or "") for page in reader.pages]
    except ParseError:
        raise
    except PdfReadError as exc:
        raise ParseError("The PDF could not be read. It may be corrupt.") from exc
    except Exception as exc:
        raise ParseError("The PDF could not be read. It may be corrupt.") from exc
    if not any(pages):
        raise ParseError("No text could be extracted from the PDF.")
    return ParsedDocument(kind="pdf", text="\n\n".join(page for page in pages if page), pages=pages)


def csv_rows(text: str) -> list[list[str]]:
    """Parse CSV text into rows."""
    try:
        return list(csv.reader(io.StringIO(text)))
    except csv.Error as exc:
        raise ParseError("The CSV file could not be parsed.") from exc
