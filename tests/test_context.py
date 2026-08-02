"""Tests for the four-layer context builder."""

import pytest

from packages.rag import ContextBuilder, RetrievedChunk


def test_context_builder_builds_four_ordered_layers_with_mock_chunks():
    """Every layer is retained in a JSON-serializable dictionary."""
    context = ContextBuilder(
        [RetrievedChunk(source="runbook.md", content="Check delayed imports.")]
    ).build(
        system_context="You are a support assistant.",
        memory_context="The user prefers concise answers.",
        task_context="Investigate the mismatch.",
    )

    assert context == {
        "system_context": "You are a support assistant.",
        "retrieved_context": [
            {"source": "runbook.md", "content": "Check delayed imports."}
        ],
        "memory_context": "The user prefers concise answers.",
        "task_context": "Investigate the mismatch.",
    }


def test_context_builder_uses_default_mock_retrieval():
    """The learning implementation is useful before a retriever is available."""
    context = ContextBuilder().build(
        system_context="You are helpful.",
        memory_context="The user is learning RAG.",
        task_context="Explain the incident.",
    )

    assert context["retrieved_context"][0]["source"] == "runbook.md"
    assert context["retrieved_context"][0]["content"]


def test_context_builder_accepts_mapping_chunks_and_copies_them():
    """Plain mappings are convenient mock retrieval fixtures."""
    chunk = {"source": "ticket.md", "content": "Batch failed."}
    builder = ContextBuilder([chunk])
    chunk["content"] = "Changed later."

    context = builder.build(
        system_context="You are helpful.",
        memory_context="No earlier conversation.",
        task_context="Find the cause.",
    )

    assert context["retrieved_context"] == [
        {"source": "ticket.md", "content": "Batch failed."}
    ]


@pytest.mark.parametrize("field", ["system_context", "memory_context", "task_context"])
def test_context_builder_rejects_blank_context_layers(field):
    """Missing prompt layers fail before an LLM request is constructed."""
    values = {
        "system_context": "You are helpful.",
        "memory_context": "No earlier conversation.",
        "task_context": "Find the cause.",
    }
    values[field] = "  "

    with pytest.raises(ValueError, match=field):
        ContextBuilder([]).build(**values)


def test_context_builder_rejects_malformed_retrieved_chunks():
    """Mock retrieval data must include meaningful source and content strings."""
    with pytest.raises(ValueError, match=r"retrieved_chunks\[1\]\.content"):
        ContextBuilder([{"source": "runbook.md", "content": ""}])
