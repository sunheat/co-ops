"""Split loaded documents into fixed-size overlapping chunks."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from hashlib import sha256

from .loaders import Document

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200


@dataclass(frozen=True)
class Chunk:
    """A retrievable slice of a document, located by character offsets."""

    id: str
    document_id: str
    source_path: str
    content: str
    start_char: int
    end_char: int
    metadata: dict[str, object] = field(default_factory=dict)


def chunk_document(
    document: Document,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Split one document into fixed-size chunks that overlap by ``overlap``.

    Boundaries are plain character offsets, so no chunk is boundary-aware yet.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if not 0 <= overlap < chunk_size:
        raise ValueError("overlap must satisfy 0 <= overlap < chunk_size")

    content = document.content
    step = chunk_size - overlap
    chunks = []
    start = 0

    while start < len(content):
        end = min(start + chunk_size, len(content))
        chunks.append(
            Chunk(
                id=_chunk_id(document.id, start, end),
                document_id=document.id,
                source_path=document.source_path,
                content=content[start:end],
                start_char=start,
                end_char=end,
                metadata={**document.metadata, "chunk_index": len(chunks)},
            )
        )
        if end == len(content):
            break
        start += step

    return chunks


def chunk_documents(
    documents: Iterable[Document],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    """Chunk documents in input order so loader ordering is preserved."""
    return [
        chunk
        for document in documents
        for chunk in chunk_document(document, chunk_size=chunk_size, overlap=overlap)
    ]


def chunk_statistics(chunks: Iterable[Chunk]) -> dict[str, int]:
    """Count chunks, their source documents, and the characters they cover."""
    chunk_list = list(chunks)
    return {
        "chunk_count": len(chunk_list),
        "document_count": len({chunk.document_id for chunk in chunk_list}),
        "total_characters": sum(len(chunk.content) for chunk in chunk_list),
    }


def _chunk_id(document_id: str, start_char: int, end_char: int) -> str:
    location = f"{document_id}:{start_char}:{end_char}"
    return f"chunk-{sha256(location.encode('utf-8')).hexdigest()}"


__all__ = [
    "DEFAULT_CHUNK_OVERLAP",
    "DEFAULT_CHUNK_SIZE",
    "Chunk",
    "chunk_document",
    "chunk_documents",
    "chunk_statistics",
]
