"""Treat retrieved text as data. Instruction-like lines are flagged and removed."""

from __future__ import annotations

import re
from dataclasses import dataclass

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ignore_instructions", re.compile(r"ignore\b.{0,80}\b(instructions|prompts|rules)", re.I)),
    ("disregard", re.compile(r"disregard\s+(the\s+)?(previous|above|system|prior)", re.I)),
    ("role_override", re.compile(r"you\s+are\s+now", re.I)),
    ("admin_mode", re.compile(r"admin\s+mode", re.I)),
    ("reveal_prompt", re.compile(r"reveal\s+the\s+(system|hidden)\s+prompt", re.I)),
    ("new_instructions", re.compile(r"new\s+instructions\s*:", re.I)),
    ("system_prompt_label", re.compile(r"system\s+prompt\s*:", re.I)),
    ("tool_directive", re.compile(r"\b(call|invoke|run)\s+the\s+\w+\s+tool\b", re.I)),
]


@dataclass(frozen=True)
class GuardedText:
    text: str
    flags: list[str]


def guard_text(text: str) -> GuardedText:
    """Wrap text and replace lines that look like instructions."""
    flags: list[str] = []
    cleaned: list[str] = []
    for line in text.splitlines():
        matched = [name for name, pattern in _PATTERNS if pattern.search(line)]
        if matched:
            flags.extend(matched)
            cleaned.append("[untrusted instruction removed]")
        else:
            cleaned.append(line)
    body = "\n".join(cleaned)
    wrapped = f"<<<UNTRUSTED_DOCUMENT_DATA>>>\n{body}\n<<<END_UNTRUSTED_DOCUMENT_DATA>>>"
    return GuardedText(text=wrapped, flags=_unique(flags))


def _unique(items: list[str]) -> list[str]:
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen
