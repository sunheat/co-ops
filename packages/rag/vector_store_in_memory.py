"""Rank chunk vectors with brute-force cosine similarity search."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import isfinite, sqrt

from .chunkers import Chunk

DEFAULT_TOP_K = 5


@dataclass(frozen=True)
class SearchResult:
    """A chunk and its cosine similarity to the query vector."""

    chunk: Chunk
    score: float


class InMemoryVectorStore:
    """Keep chunk vectors in a list and scan them linearly per query.

    Cosine similarity is computed with the standard library, so the store has
    no vector-database or numeric-library dependency. Vectors are kept for the
    lifetime of the process only; rebuilding the store means re-embedding the
    corpus.
    """

    def __init__(self) -> None:
        self._entries: list[tuple[Chunk, tuple[float, ...], float]] = []
        self._dimension: int | None = None

    def add(self, chunk: Chunk, vector: Sequence[float]) -> None:
        """Store one chunk with its embedding vector.

        Raises:
            ValueError: If the vector is empty, non-finite, zero-norm, or has
                a different dimension than the vectors already stored.
        """
        stored = _validated_vector(vector)
        if self._dimension is None:
            self._dimension = len(stored)
        else:
            self._check_dimension(len(stored), "vector")
        self._entries.append((chunk, stored, _norm(stored)))

    def search(
        self,
        vector: Sequence[float],
        top_k: int = DEFAULT_TOP_K,
    ) -> list[SearchResult]:
        """Return up to ``top_k`` chunks ordered by descending cosine similarity.

        Ties keep insertion order, so ranking is deterministic across runs.
        """
        if top_k < 1:
            raise ValueError("top_k must be positive")
        query = _validated_vector(vector)
        self._check_dimension(len(query), "query")

        query_norm = _norm(query)
        # One linear scan per query; revisit with a vector database or a
        # numeric library once the corpus outgrows a few thousand chunks.
        results = [
            SearchResult(chunk=chunk, score=_dot(query, stored) / (query_norm * norm))
            for chunk, stored, norm in self._entries
        ]
        results.sort(key=lambda result: result.score, reverse=True)
        return results[:top_k]

    def __len__(self) -> int:
        """Number of stored chunk vectors."""
        return len(self._entries)

    def _check_dimension(self, length: int, label: str) -> None:
        if self._dimension is not None and length != self._dimension:
            raise ValueError(
                f"{label} dimension {length} does not match "
                f"store dimension {self._dimension}"
            )


def _validated_vector(vector: Sequence[float]) -> tuple[float, ...]:
    values = tuple(float(value) for value in vector)
    if not values:
        raise ValueError("vector must contain at least one value")
    if any(not isfinite(value) for value in values):
        raise ValueError("vector values must be finite")
    if _norm(values) == 0.0:
        raise ValueError("vector must have a non-zero norm")
    return values


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _norm(vector: Sequence[float]) -> float:
    return sqrt(sum(value * value for value in vector))


__all__ = [
    "DEFAULT_TOP_K",
    "InMemoryVectorStore",
    "SearchResult",
]
