"""The sample set is present and covers the required question types."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "eval"
REQUIRED = {"factual", "multi_doc", "conflict", "unanswerable", "injection", "follow_up"}


def test_dataset_covers_required_types() -> None:
    dataset = json.loads((ROOT / "dataset.json").read_text())
    questions = dataset["questions"]
    assert len(questions) >= 25
    assert REQUIRED <= {item["type"] for item in questions}
    names = {path.name for path in (ROOT / "corpus").iterdir() if path.is_file()}
    for item in questions:
        for filename in item["expected_files"]:
            assert filename in names
        if item["type"] == "conflict":
            assert item["conflict"] is True
        if item["type"] == "unanswerable":
            assert item["insufficient_evidence"] is True
