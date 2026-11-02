"""Upload checks: extension, size, declared type, and content sniffing."""

from __future__ import annotations

import re
from pathlib import Path

from app.core.errors import ValidationFailed
from app.domain import DocumentKind

_EXTENSIONS: dict[str, DocumentKind] = {
    ".pdf": "pdf",
    ".txt": "txt",
    ".md": "md",
    ".csv": "csv",
}

_ALLOWED_TYPES: dict[DocumentKind, set[str]] = {
    "pdf": {"application/pdf", "application/octet-stream", "binary/octet-stream", ""},
    "txt": {"text/plain", "application/octet-stream", ""},
    "md": {"text/markdown", "text/plain", "text/x-markdown", "application/octet-stream", ""},
    "csv": {
        "text/csv",
        "application/csv",
        "text/plain",
        "application/vnd.ms-excel",
        "application/octet-stream",
        "",
    },
}

_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def safe_filename(filename: str | None) -> str:
    """Drop any directory portion and characters that are unsafe in a label."""
    base = Path(filename or "upload").name
    cleaned = _UNSAFE_NAME.sub("_", base).strip("._")
    return (cleaned or "upload")[:180]


def validate_upload(
    filename: str | None, content_type: str | None, data: bytes, max_bytes: int
) -> DocumentKind:
    """Accept a supported document or raise ValidationFailed."""
    if not data:
        raise ValidationFailed("The file is empty.")
    if len(data) > max_bytes:
        raise ValidationFailed(f"Files must be {max_bytes // (1024 * 1024)} MB or smaller.")
    extension = Path(filename or "").suffix.lower()
    kind = _EXTENSIONS.get(extension)
    if kind is None:
        raise ValidationFailed("Upload a PDF, TXT, MD, or CSV file.")
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared not in _ALLOWED_TYPES[kind]:
        raise ValidationFailed(
            f"Content type {declared or 'unknown'} does not match a {extension} file."
        )
    _sniff(kind, data)
    return kind


def _sniff(kind: DocumentKind, data: bytes) -> None:
    if kind == "pdf":
        if not data.startswith(b"%PDF"):
            raise ValidationFailed("The file does not look like a PDF.")
        return
    if data.startswith(b"%PDF") or data.startswith(b"\x7fELF") or data.startswith(b"MZ"):
        raise ValidationFailed("The file contents do not match its extension.")
    if b"\x00" in data:
        raise ValidationFailed("The text file contains binary data.")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationFailed("The text file must be UTF-8.") from exc
