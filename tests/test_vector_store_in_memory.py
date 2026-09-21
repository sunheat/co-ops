"""Tests for brute-force cosine similarity search over in-memory vectors."""

import pytest

from packages.rag import Chunk, InMemoryVectorStore
from packages.rag.vector_store_in_memory import DEFAULT_TOP_K


def make_chunk(chunk_id: str, content: str = "content") -> Chunk:
    """Build a chunk with a stable test identity."""
    return Chunk(
        id=chunk_id,
        document_id="doc-test",
        source_path="data/sample_docs/example.md",
        content=content,
        start_char=0,
        end_char=len(content),
        metadata={},
    )


def make_store(
    entries: list[tuple[str, tuple[float, ...]]],
) -> InMemoryVectorStore:
    """Build a store from (chunk_id, vector) pairs in insertion order."""
    store = InMemoryVectorStore()
    for chunk_id, vector in entries:
        store.add(make_chunk(chunk_id), vector)
    return store


def test_search_ranks_by_descending_cosine_similarity():
    """The most similar vector ranks first and scores match cosine values."""
    store = make_store(
        [
            ("chunk-orthogonal", (0.0, 1.0, 0.0)),
            ("chunk-diagonal", (1.0, 1.0, 0.0)),
            ("chunk-identical", (1.0, 0.0, 0.0)),
        ]
    )

    results = store.search((1.0, 0.0, 0.0))

    assert [result.chunk.id for result in results] == [
        "chunk-identical",
        "chunk-diagonal",
        "chunk-orthogonal",
    ]
    assert results[0].score == pytest.approx(1.0)
    assert results[1].score == pytest.approx(1 / 2**0.5)
    assert results[2].score == pytest.approx(0.0)


def test_search_computes_cosine_not_raw_dot_product():
    """Magnitude differences do not change the score of parallel vectors."""
    store = make_store([("chunk-small", (1.0, 2.0, 3.0))])

    results = store.search((4.0, 5.0, 6.0))

    dot_product = 4 * 1 + 5 * 2 + 6 * 3
    expected = dot_product / ((14**0.5) * (77**0.5))
    assert results[0].score == pytest.approx(expected)


def test_search_limits_results_to_top_k_and_defaults():
    """top_k slices the ranking, and the default is used when omitted."""
    entries = [(f"chunk-{index}", (1.0, float(index))) for index in range(8)]
    store = make_store(entries)

    assert len(store.search((1.0, 1.0), top_k=3)) == 3
    assert len(store.search((1.0, 1.0))) == DEFAULT_TOP_K
    assert len(store.search((1.0, 1.0), top_k=100)) == len(entries)


def test_identical_scores_keep_insertion_order():
    """Equal vectors stay deterministic instead of reordering between runs."""
    store = make_store(
        [
            ("chunk-first", (1.0, 0.0)),
            ("chunk-second", (2.0, 0.0)),
        ]
    )

    results = store.search((1.0, 0.0))

    assert [result.chunk.id for result in results] == ["chunk-first", "chunk-second"]
    assert results[0].score == pytest.approx(results[1].score)


def test_search_on_empty_store_returns_no_results():
    """An unindexed store answers every query with an empty ranking."""
    store = InMemoryVectorStore()

    assert len(store) == 0
    assert store.search((1.0, 0.0)) == []


def test_store_reports_length_after_each_add():
    """The store counts every added chunk vector."""
    store = make_store([("chunk-a", (1.0, 0.0))])

    assert len(store) == 1

    store.add(make_chunk("chunk-b"), (0.0, 1.0))

    assert len(store) == 2


def test_vectors_must_match_the_store_dimension():
    """Mixed embedding models or dimensions fail instead of scoring garbage."""
    store = make_store([("chunk-a", (1.0, 0.0))])

    with pytest.raises(ValueError, match="dimension"):
        store.add(make_chunk("chunk-b"), (1.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="dimension"):
        store.search((1.0, 0.0, 0.0))
    assert len(store) == 1


@pytest.mark.parametrize(
    "vector",
    [(), (0.0, 0.0), (float("nan"), 1.0), (float("inf"), 1.0), ("not-a-number",)],
)
def test_add_rejects_unusable_vectors(vector):
    """Empty, zero-norm, non-finite, and non-numeric vectors are rejected."""
    store = InMemoryVectorStore()

    with pytest.raises(ValueError):
        store.add(make_chunk("chunk-a"), vector)


def test_search_rejects_unusable_queries_and_top_k():
    """Invalid queries fail the same way as invalid stored vectors."""
    store = make_store([("chunk-a", (1.0, 0.0))])

    with pytest.raises(ValueError):
        store.search((0.0, 0.0))
    with pytest.raises(ValueError, match="top_k"):
        store.search((1.0, 0.0), top_k=0)
    with pytest.raises(ValueError, match="top_k"):
        store.search((1.0, 0.0), top_k=-1)


@pytest.mark.parametrize("scale", [1e200, 1e-200])
def test_search_handles_finite_vectors_at_extreme_scales(scale):
    """Finite non-zero vectors keep their cosine score at extreme magnitudes."""
    store = make_store(
        [
            ("chunk-axis", (scale, 0.0)),
            ("chunk-diagonal", (scale, scale)),
        ]
    )

    results = store.search((scale, scale))

    assert [result.chunk.id for result in results] == ["chunk-diagonal", "chunk-axis"]
    assert [result.score for result in results] == pytest.approx([1.0, 1 / 2**0.5])
