"""Tests for the citation schema, parsing, and first-pass validation."""

import json

import pytest
from pydantic import ValidationError

from packages.rag import (
    CitedAnswer,
    CitedSource,
    cited_answer_output_instruction,
    parse_cited_answer,
    validate_citations,
)
from tests.test_rag_pipeline import MARGIN_PATH, RUNBOOK_PATH, make_chunk


def make_citation(source_path: str, chunk_id: str) -> CitedSource:
    """Build one model citation."""
    return CitedSource(source_path=source_path, chunk_id=chunk_id)


def cited_json(**overrides: object) -> str:
    """Return one schema-conforming JSON payload, with optional overrides."""
    payload: dict = {
        "answer": "Margin is calculated in MarginCalculator.",
        "sources": [{"source_path": MARGIN_PATH, "chunk_id": "chunk-margin"}],
        "confidence": "high",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_output_instruction_demands_json_with_citation_fields():
    """The instruction pins the JSON shape and the no-fabrication rule."""
    instruction = cited_answer_output_instruction()

    assert '"answer"' in instruction
    assert '"source_path"' in instruction
    assert '"chunk_id"' in instruction
    assert '"low"' in instruction
    assert "only a valid JSON object" in instruction
    assert "provided context" in instruction


def test_parse_cited_answer_returns_validated_structured_answer():
    """Schema-conforming JSON parses into the structured answer model."""
    cited = parse_cited_answer(cited_json())

    assert isinstance(cited, CitedAnswer)
    assert cited.answer == "Margin is calculated in MarginCalculator."
    assert cited.sources == [make_citation(MARGIN_PATH, "chunk-margin")]
    assert cited.confidence == "high"


def test_parse_cited_answer_rejects_non_json_output():
    """Free-text model output fails with a clear ValueError."""
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_cited_answer("Margin is calculated in MarginCalculator.")


def test_parse_cited_answer_rejects_schema_violations():
    """Unknown confidence values and missing fields fail validation."""
    with pytest.raises(ValidationError):
        parse_cited_answer(cited_json(confidence="certain"))
    with pytest.raises(ValidationError):
        parse_cited_answer(cited_json(sources=[{"source_path": MARGIN_PATH}]))


def test_validate_citations_accepts_citations_grounded_in_retrieval():
    """A citation survives when chunk id and source path both match."""
    retrieved = [
        make_chunk("chunk-margin", MARGIN_PATH, "Margin content"),
        make_chunk("chunk-runbook", RUNBOOK_PATH, "Runbook content"),
    ]

    valid, invalid = validate_citations(
        [make_citation(MARGIN_PATH, "chunk-margin")], retrieved
    )

    assert [source.chunk_id for source in valid] == ["chunk-margin"]
    assert invalid == []


def test_validate_citations_rejects_fabricated_and_mismatched_sources():
    """Unknown chunk ids and wrong paths are rejected, but exact duplicates are skipped."""
    retrieved = [make_chunk("chunk-margin", MARGIN_PATH, "Margin content")]

    valid, invalid = validate_citations(
        [
            make_citation("data/fabricated.md", "chunk-ghost"),
            make_citation(MARGIN_PATH, "chunk-margin"),
            make_citation(MARGIN_PATH, "chunk-margin"),
            make_citation(RUNBOOK_PATH, "chunk-margin"),
        ],
        retrieved,
    )

    assert valid == [make_citation(MARGIN_PATH, "chunk-margin")]
    assert invalid == [
        make_citation("data/fabricated.md", "chunk-ghost"),
        make_citation(RUNBOOK_PATH, "chunk-margin"),
    ]
