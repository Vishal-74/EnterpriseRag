"""Map retrieved chunks to the citation objects returned by the API."""

from __future__ import annotations

from app.schemas.chat import Citation
from app.services.retrieval.types import ScoredChunk


def citation_for(item: ScoredChunk) -> Citation:
    """Build a citation with a short snippet."""
    snippet = " ".join(item.chunk.content.split())
    if len(snippet) > 400:
        snippet = snippet[:400].rstrip() + "…"
    score = item.vector_similarity if item.vector_similarity is not None else item.fusion_score
    return Citation(
        document_id=item.chunk.document_id,
        document_name=item.document_name,
        chunk_id=item.chunk.id,
        page_start=item.chunk.page_start,
        page_end=item.chunk.page_end,
        section=item.chunk.section,
        row_start=item.chunk.row_start,
        row_end=item.chunk.row_end,
        snippet=snippet,
        score=round(float(score), 4),
    )


def citations_for_ids(items: list[ScoredChunk], chunk_ids: list[str]) -> list[Citation]:
    """Keep cited chunks in the model's order and drop unknown ids."""
    by_id = {str(item.chunk.id): item for item in items}
    chosen: list[Citation] = []
    seen: set[str] = set()
    for chunk_id in chunk_ids:
        if chunk_id in seen or chunk_id not in by_id:
            continue
        seen.add(chunk_id)
        chosen.append(citation_for(by_id[chunk_id]))
    return chosen
