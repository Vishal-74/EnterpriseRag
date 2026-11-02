"""Split parsed documents into overlapping chunks with location metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.ingestion.parsers import csv_rows

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class TextSlice:
    text: str
    start: int
    end: int


@dataclass(frozen=True)
class ChunkDraft:
    index: int
    content: str
    page_start: int | None
    page_end: int | None
    section: str | None
    row_start: int | None
    row_end: int | None


def split_text(text: str, size: int, overlap: int) -> list[TextSlice]:
    """Split text on paragraph, line, and sentence boundaries.

    The window always moves forward, so a large document cannot loop.
    """
    if size <= 0:
        raise ValueError("chunk size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be >= 0 and smaller than chunk size")
    if not text.strip():
        return []

    slices: list[TextSlice] = []
    start = 0
    length = len(text)
    while start < length and text[start].isspace():
        start += 1
    while start < length:
        hard_end = min(start + size, length)
        cut = length if hard_end >= length else _best_cut(text, start, hard_end)
        if cut <= start:
            cut = hard_end
        piece = text[start:cut].strip()
        if piece:
            slices.append(TextSlice(piece, start, cut))
        if cut >= length:
            break
        next_start = cut - overlap
        if next_start <= start:
            next_start = cut
        start = next_start
    return slices


def chunk_plain(
    text: str, size: int, overlap: int, *, section: str | None = None
) -> list[ChunkDraft]:
    """Chunk prose that has no page or row metadata."""
    drafts: list[ChunkDraft] = []
    for index, piece in enumerate(split_text(text, size, overlap)):
        drafts.append(
            ChunkDraft(
                index=index,
                content=piece.text,
                page_start=None,
                page_end=None,
                section=section,
                row_start=None,
                row_end=None,
            )
        )
    return drafts


def chunk_pdf(pages: list[str], size: int, overlap: int) -> list[ChunkDraft]:
    """Chunk a PDF while remembering which pages each slice touches."""
    parts: list[str] = []
    spans: list[tuple[int, int, int]] = []
    cursor = 0
    for number, page in enumerate(pages, start=1):
        if parts:
            parts.append("\n\n")
            cursor += 2
        begin = cursor
        parts.append(page)
        cursor += len(page)
        spans.append((begin, cursor, number))
    full = "".join(parts)
    drafts: list[ChunkDraft] = []
    for index, piece in enumerate(split_text(full, size, overlap)):
        touched = [page for begin, end, page in spans if end > piece.start and begin < piece.end]
        drafts.append(
            ChunkDraft(
                index=index,
                content=piece.text,
                page_start=min(touched) if touched else None,
                page_end=max(touched) if touched else None,
                section=None,
                row_start=None,
                row_end=None,
            )
        )
    return drafts


def chunk_markdown(text: str, size: int, overlap: int) -> list[ChunkDraft]:
    """Chunk Markdown under the heading that introduced each section."""
    matches = list(_HEADING.finditer(text))
    if not matches:
        return chunk_plain(text, size, overlap)
    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        preamble = text[: matches[0].start()]
        if preamble.strip():
            sections.append(("Introduction", preamble))
    for index, match in enumerate(matches):
        title = match.group(2).strip()[:300]
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((title, text[match.start() : end]))
    drafts: list[ChunkDraft] = []
    for title, body in sections:
        for piece in split_text(body, size, overlap):
            drafts.append(
                ChunkDraft(
                    index=len(drafts),
                    content=piece.text,
                    page_start=None,
                    page_end=None,
                    section=title,
                    row_start=None,
                    row_end=None,
                )
            )
    return drafts


def chunk_csv(text: str, rows_per_chunk: int, row_overlap: int) -> list[ChunkDraft]:
    """Group CSV data rows. Every chunk repeats the header and cites row numbers."""
    rows = csv_rows(text)
    if not rows:
        return []
    header = rows[0]
    data = rows[1:]
    if not data:
        return [
            ChunkDraft(
                index=0,
                content=_format_csv(header, [], file_row=2),
                page_start=None,
                page_end=None,
                section=None,
                row_start=1,
                row_end=1,
            )
        ]
    step = max(1, rows_per_chunk - row_overlap)
    drafts: list[ChunkDraft] = []
    start = 0
    while start < len(data):
        window = data[start : start + rows_per_chunk]
        file_start = start + 2
        file_end = start + 1 + len(window)
        drafts.append(
            ChunkDraft(
                index=len(drafts),
                content=_format_csv(header, window, file_row=file_start),
                page_start=None,
                page_end=None,
                section=None,
                row_start=file_start,
                row_end=file_end,
            )
        )
        if start + rows_per_chunk >= len(data):
            break
        start += step
    return drafts


def _best_cut(text: str, start: int, hard_end: int) -> int:
    window = text[start:hard_end]
    for separator in ("\n\n", "\n", ". ", " "):
        index = window.rfind(separator)
        if index > len(window) // 4:
            return start + index + len(separator)
    return hard_end


def _format_csv(header: list[str], data_rows: list[list[str]], *, file_row: int) -> str:
    header_line = ", ".join(header)
    lines = [f"Columns: {header_line}"]
    for offset, row in enumerate(data_rows):
        pairs = []
        for column, value in enumerate(row):
            name = header[column] if column < len(header) else f"column_{column + 1}"
            pairs.append(f"{name}={value}")
        lines.append(f"Row {file_row + offset}: " + "; ".join(pairs))
    return "\n".join(lines)
