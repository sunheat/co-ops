"""Structured citation output schema and first-pass citation validation."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ValidationError

from .chunkers import Chunk


class CitedSource(BaseModel):
    """One source citation the model claims its answer is built on."""

    source_path: str
    chunk_id: str


class CitedAnswer(BaseModel):
    """A structured RAG answer that must cite the sources behind its claims."""

    answer: str
    sources: list[CitedSource]
    confidence: Literal["low", "medium", "high"]


def cited_answer_output_instruction() -> str:
    """Return an instruction that asks the model for schema-conforming JSON."""
    schema = json.dumps(CitedAnswer.model_json_schema(), indent=2)
    return (
        "Return only a valid JSON object with no Markdown fences or extra text. "
        "Cite only sources taken verbatim from the provided context, and set "
        "confidence to how well the context answers the question. It must "
        "conform to this JSON Schema:\n"
        f"{schema}"
    )


def parse_cited_answer(response_text: str) -> CitedAnswer:
    """Parse model JSON output and validate it as a ``CitedAnswer``.

    Invalid JSON raises ``ValueError``. JSON that does not match the schema
    raises Pydantic's ``ValidationError``.
    """
    if not isinstance(response_text, str):
        raise TypeError("response_text must be a string")

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response is not valid JSON") from exc

    return CitedAnswer.model_validate(payload)


def validate_citations(
    citations: Sequence[CitedSource],
    retrieved: Sequence[Chunk],
) -> tuple[list[CitedSource], list[CitedSource]]:
    """Split model citations into ones grounded in retrieval and fabrications.

    A citation is valid only when its chunk id was retrieved and the cited
    source path matches that chunk's actual path. Duplicates are collapsed
    into one valid source. Returns ``(valid, invalid)`` in citation order.
    """
    known_paths = {chunk.id: chunk.source_path for chunk in retrieved}
    valid: list[CitedSource] = []
    invalid: list[CitedSource] = []
    seen_chunk_ids: set[str] = set()

    for citation in citations:
        if (
            known_paths.get(citation.chunk_id) == citation.source_path
            and citation.chunk_id not in seen_chunk_ids
        ):
            valid.append(citation)
            seen_chunk_ids.add(citation.chunk_id)
        else:
            invalid.append(citation)

    return valid, invalid


__all__ = [
    "CitedAnswer",
    "CitedSource",
    "cited_answer_output_instruction",
    "parse_cited_answer",
    "validate_citations",
]
