"""Build a bounded view of a conversation for the next question."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import Settings
from app.models.conversation import Message
from app.services.llm.tokens import count_text


@dataclass(frozen=True)
class MemoryContext:
    summary: str
    recent_lines: list[str]
    history_tokens: int
    document_names: list[str]


def build_memory(summary: str, messages: list[Message], settings: Settings) -> MemoryContext:
    """Keep the rolling summary plus the newest turns that fit the token budget."""
    window = messages[-settings.memory_recent_turns :]
    selected: list[Message] = []
    used = count_text(summary)
    for message in reversed(window):
        cost = count_text(message.content) + 4
        if selected and used + cost > settings.memory_token_budget:
            break
        selected.append(message)
        used += cost
    selected.reverse()
    names: list[str] = []
    for message in selected:
        for citation in message.citations or []:
            name = str(citation.get("document_name", "")).strip()
            if name and name not in names:
                names.append(name)
    lines = [f"{message.role}: {message.content}" for message in selected]
    return MemoryContext(
        summary=summary.strip(),
        recent_lines=lines,
        history_tokens=used,
        document_names=names,
    )


def render_memory(memory: MemoryContext) -> str:
    """Render memory as plain text for a prompt."""
    parts: list[str] = []
    if memory.summary:
        parts.append(f"Earlier summary:\n{memory.summary}")
    if memory.document_names:
        parts.append("Documents already discussed: " + ", ".join(memory.document_names))
    if memory.recent_lines:
        parts.append("Recent turns:\n" + "\n".join(memory.recent_lines))
    return "\n\n".join(parts) if parts else "No earlier conversation."
