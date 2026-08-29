"""Retrieval-augmented generation building blocks.

The context exports remain here as a compatibility facade. New application
code should import them from ``packages.context``.
"""

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
    "ContextBuilder",
    "Document",
    "RetrievedChunk",
    "RetrievedContext",
    "SourceType",
    "load_code_files",
    "load_markdown_docs",
    "load_text_docs",
]
