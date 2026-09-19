"""Retrieval-augmented generation building blocks.

The context exports remain here as a compatibility facade. New application
code should import them from ``packages.context``.
"""

from .chunkers import (
    Chunk,
    chunk_document,
    chunk_documents,
    chunk_statistics,
)
from .context import BuiltContext, ContextBuilder, RetrievedChunk, RetrievedContext
from .loaders import (
    Document,
    SourceType,
    load_code_files,
    load_markdown_docs,
    load_text_docs,
)

__all__ = [
    "BuiltContext",
    "Chunk",
    "ContextBuilder",
    "Document",
    "RetrievedChunk",
    "RetrievedContext",
    "SourceType",
    "chunk_document",
    "chunk_documents",
    "chunk_statistics",
    "load_code_files",
    "load_markdown_docs",
    "load_text_docs",
]
