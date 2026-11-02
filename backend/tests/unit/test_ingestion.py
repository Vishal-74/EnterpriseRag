"""Parsers, chunking, upload validation, and hashing."""

from __future__ import annotations

from app.core.errors import ParseError, ValidationFailed
from app.services.hashing import sha256_bytes, sha256_text
from app.services.ingestion.chunker import chunk_csv, chunk_markdown, chunk_pdf, split_text
from app.services.ingestion.parsers import parse_document
from app.services.ingestion.validation import safe_filename, validate_upload


def test_hash_is_stable() -> None:
    assert sha256_text("pump") == sha256_text("pump")
    assert sha256_bytes(b"abc") != sha256_bytes(b"abd")


def test_safe_filename_drops_path_and_odd_characters() -> None:
    assert safe_filename("../../etc/passwd") == "passwd"
    assert "/" not in safe_filename("a b?.txt")


def test_split_text_moves_forward_on_a_long_string() -> None:
    slices = split_text("word " * 5000, size=120, overlap=20)
    assert len(slices) > 10
    assert slices[0].text
    assert slices[-1].end <= len("word " * 5000)


def test_split_text_rejects_overlap_that_would_loop() -> None:
    try:
        split_text("hello", size=10, overlap=10)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_markdown_chunks_keep_the_heading() -> None:
    text = "# Cooling\n\nThe pump failed.\n\n# Power\n\nThe breaker tripped.\n"
    drafts = chunk_markdown(text, size=80, overlap=10)
    sections = {draft.section for draft in drafts}
    assert "Cooling" in sections
    assert "Power" in sections


def test_csv_chunks_repeat_the_header_and_cite_rows() -> None:
    text = "asset,result\nP-441,replaced\nT-19,drift\n"
    drafts = chunk_csv(text, rows_per_chunk=1, row_overlap=0)
    assert drafts[0].row_start == 2
    assert "asset" in drafts[0].content
    assert drafts[1].row_start == 3


def test_pdf_chunks_record_page_numbers() -> None:
    drafts = chunk_pdf(["page one " * 30, "page two is short"], size=80, overlap=10)
    assert drafts[0].page_start == 1
    assert any(draft.page_end == 2 for draft in drafts)


def test_txt_parser_normalizes_newlines() -> None:
    parsed = parse_document("txt", b"alpha\r\nbeta")
    assert parsed.text == "alpha\nbeta"


def test_corrupt_pdf_is_rejected() -> None:
    try:
        parse_document("pdf", b"%PDF-1.4\nnot-a-real-pdf")
    except ParseError as exc:
        assert "corrupt" in exc.message.lower() or "read" in exc.message.lower()
        return
    raise AssertionError("expected ParseError")


def test_upload_validation_rejects_empty_and_mismatched_bytes() -> None:
    try:
        validate_upload("notes.txt", "text/plain", b"", 1000)
    except ValidationFailed:
        pass
    else:
        raise AssertionError("empty file should fail")
    try:
        validate_upload("notes.txt", "text/plain", b"%PDF-1.4", 1000)
    except ValidationFailed:
        return
    raise AssertionError("pdf bytes with a txt name should fail")


def test_upload_validation_accepts_plain_text() -> None:
    assert validate_upload("notes.txt", "text/plain", b"hello", 1000) == "txt"
