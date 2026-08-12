"""Retrieval-augmented generation building blocks.

The context exports remain here as a compatibility facade. New application
code should import them from ``packages.context``.
"""

from .context import BuiltContext, ContextBuilder, RetrievedChunk, RetrievedContext

__all__ = ["BuiltContext", "ContextBuilder", "RetrievedChunk", "RetrievedContext"]
