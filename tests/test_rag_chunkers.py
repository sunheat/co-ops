"""Tests for fixed-size chunking of loaded RAG documents."""

from itertools import pairwise

import pytest

from packages.rag import (
    Chunk,
    Document,
    chunk_document,
    chunk_documents,
    chunk_statistics,
    load_code_files,
    load_markdown_docs,
)
from packages.rag.chunkers import DEFAULT_CHUNK_SIZE


def make_document(
    content: str, *, document_id: str = "doc-test", **metadata: object
) -> Document:
    """Build a document with a stable test identity."""
    return Document(
        id=document_id,
        source_path="data/sample_docs/example.md",
        source_type="doc",
        content=content,
        metadata=dict(metadata),
    )


def test_chunks_use_fixed_size_overlap_and_exact_offsets():
    """Chunk boundaries step by chunk_size - overlap and cover the document."""
    content = "abcdefghijklmnopqrstuvwxy"  # 25 characters
    document = make_document(content)

    chunks = chunk_document(document, chunk_size=10, overlap=4)

    assert [(chunk.start_char, chunk.end_char) for chunk in chunks] == [
        (0, 10),
        (6, 16),
        (12, 22),
        (18, 25),
    ]
    assert [chunk.content for chunk in chunks] == [
        content[start:end] for start, end in ((0, 10), (6, 16), (12, 22), (18, 25))
    ]
    for previous, following in pairwise(chunks):
        assert previous.content[-4:] == following.content[:4]
        assert following.start_char == previous.end_char - 4


def test_chunk_metadata_carries_document_metadata_and_index():
    """Each chunk keeps its document metadata and its position in the document."""
    document = make_document("0123456789", format="markdown", extension=".md")

    chunks = chunk_document(document, chunk_size=4, overlap=0)

    assert [chunk.metadata for chunk in chunks] == [
        {"format": "markdown", "extension": ".md", "chunk_index": index}
        for index in range(3)
    ]
    assert all(chunk.document_id == "doc-test" for chunk in chunks)
    assert all(chunk.source_path == "data/sample_docs/example.md" for chunk in chunks)


def test_short_document_yields_one_chunk_and_empty_document_yields_none():
    """Documents shorter than the window produce one chunk, empty ones none."""
    short_document = make_document("short")
    empty_document = make_document("")

    short_chunks = chunk_document(short_document, chunk_size=100, overlap=20)

    assert short_chunks == [
        Chunk(
            id=short_chunks[0].id,
            document_id="doc-test",
            source_path="data/sample_docs/example.md",
            content="short",
            start_char=0,
            end_char=5,
            metadata={"chunk_index": 0},
        )
    ]
    assert chunk_document(empty_document) == []


def test_chunk_ids_are_unique_and_stable_across_runs():
    """Repeated chunking returns the same IDs and never collides."""
    document = make_document("x" * 40)

    first_run = chunk_document(document, chunk_size=15, overlap=5)
    second_run = chunk_document(document, chunk_size=15, overlap=5)

    assert [chunk.id for chunk in first_run] == [chunk.id for chunk in second_run]
    assert len({chunk.id for chunk in first_run}) == len(first_run)


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [(0, 0), (-1, 0), (10, -1), (10, 10), (10, 11)],
)
def test_invalid_chunk_parameters_raise_value_error(chunk_size: int, overlap: int):
    """Unusable window sizes fail explicitly instead of looping forever."""
    document = make_document("0123456789")

    with pytest.raises(ValueError):
        chunk_document(document, chunk_size=chunk_size, overlap=overlap)


@pytest.mark.parametrize(
    ("chunk_size", "overlap"),
    [(0, 0), (-1, 0), (10, -1), (10, 10), (10, 11)],
)
def test_chunk_documents_rejects_invalid_parameters_for_empty_input(
    chunk_size: int, overlap: int
):
    """Invalid batch settings fail even when there are no documents to chunk."""
    with pytest.raises(ValueError):
        chunk_documents([], chunk_size=chunk_size, overlap=overlap)


def test_chunk_documents_preserves_input_order_and_respects_window():
    """Batching keeps loader order and never exceeds the configured window."""
    documents = [
        make_document("a" * 16, document_id="doc-a"),
        make_document("b" * 16, document_id="doc-b"),
    ]

    chunks = chunk_documents(documents, chunk_size=10, overlap=5)

    assert [
        (chunk.document_id, chunk.start_char, len(chunk.content)) for chunk in chunks
    ] == [
        ("doc-a", 0, 10),
        ("doc-a", 5, 10),
        ("doc-a", 10, 6),
        ("doc-b", 0, 10),
        ("doc-b", 5, 10),
        ("doc-b", 10, 6),
    ]
    assert all(len(chunk.content) <= 10 for chunk in chunks)


def test_default_corpus_chunks_match_their_source_documents():
    """Every chunk of the sample corpus is a real slice of its source file."""
    documents = [*load_markdown_docs(), *load_code_files()]
    documents_by_id = {document.id: document for document in documents}

    chunks = chunk_documents(documents)

    assert chunks
    assert len({chunk.id for chunk in chunks}) == len(chunks)
    for chunk in chunks:
        source = documents_by_id[chunk.document_id]
        assert chunk.content == source.content[chunk.start_char : chunk.end_char]
        assert len(chunk.content) <= DEFAULT_CHUNK_SIZE
        assert chunk.source_path == source.source_path


def test_chunk_statistics_counts_chunks_documents_and_characters():
    """Statistics summarize one indexing run for reporting."""
    documents = [
        make_document("a" * 8, document_id="doc-a"),
        make_document("b" * 12, document_id="doc-b"),
    ]

    statistics = chunk_statistics(chunk_documents(documents, chunk_size=8, overlap=0))

    assert statistics == {
        "chunk_count": 3,
        "document_count": 2,
        "total_characters": 8 + 8 + 4,
    }
    assert chunk_statistics([]) == {
        "chunk_count": 0,
        "document_count": 0,
        "total_characters": 0,
    }
