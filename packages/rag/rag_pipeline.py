"""Minimal RAG pipeline: retrieve top-k chunks, build context, call the model."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from packages.llm import EmbeddingClient, LLMClient, Usage
from packages.prompt import ContextBlock, MessageBuilder

from .chunkers import Chunk
from .vector_store_in_memory import DEFAULT_TOP_K, InMemoryVectorStore, SearchResult

EMBED_BATCH_SIZE = 100  # Gemini rejects embedding batches above 100 inputs
DEFAULT_TEMPERATURE = 0.2  # grounded answers want little sampling

SYSTEM_PROMPT = (
    "You are an enterprise support assistant. Answer the question using only "
    "the provided context, and name the source path behind every claim. If the "
    "context does not answer the question, say so instead of guessing."
)

OUTPUT_INSTRUCTION = (
    "Answer in one short paragraph, then list the source paths you used under "
    "a 'Sources:' line."
)


@dataclass(frozen=True)
class RagSource:
    """A retrieved chunk an answer can cite, at chunk granularity."""

    source_path: str
    chunk_id: str


@dataclass(frozen=True)
class RagAnswer:
    """One generated answer with the evidence it was built from."""

    answer: str
    sources: list[RagSource]
    retrieved: list[SearchResult]
    usage: Usage | None = None
    latency_ms: float | None = None


class RagPipeline:
    """Answer questions from chunks indexed in memory.

    Index the corpus once with ``index()``, then call ``ask()`` per question.
    Retrieval is brute-force cosine similarity (see ``InMemoryVectorStore``),
    so the pipeline stays a readable from-scratch RAG loop rather than a
    wrapper around a vector database.
    """

    def __init__(
        self,
        *,
        embedding_client: EmbeddingClient,
        embedding_model: str,
        llm_client: LLMClient,
        llm_model: str,
        top_k: int = DEFAULT_TOP_K,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> None:
        self._embedding_client = embedding_client
        self._embedding_model = embedding_model
        self._llm_client = llm_client
        self._llm_model = llm_model
        self._top_k = top_k
        self._temperature = temperature
        self._store = InMemoryVectorStore()

    @property
    def chunk_count(self) -> int:
        """Number of chunks indexed so far."""
        return len(self._store)

    def index(self, chunks: Sequence[Chunk]) -> None:
        """Embed chunks in provider-sized batches and add them to the store."""
        for start in range(0, len(chunks), EMBED_BATCH_SIZE):
            batch = chunks[start : start + EMBED_BATCH_SIZE]
            response = self._embedding_client.embed(
                [chunk.content for chunk in batch],
                model=self._embedding_model,
            )
            for chunk, vector in zip(batch, response.embeddings, strict=True):
                self._store.add(chunk, vector)

    def ask(self, question: str) -> RagAnswer:
        """Retrieve the chunks closest to the question and generate an answer."""
        if not question.strip():
            raise ValueError("question must be a non-empty string")

        query_response = self._embedding_client.embed(
            question,
            model=self._embedding_model,
        )
        retrieved = self._store.search(query_response.embeddings[0], top_k=self._top_k)

        messages = MessageBuilder().build(
            system=SYSTEM_PROMPT,
            context=[
                ContextBlock(
                    label=result.chunk.source_path,
                    content=result.chunk.content,
                )
                for result in retrieved
            ],
            task=question,
            output_instruction=OUTPUT_INSTRUCTION,
        )
        response = self._llm_client.chat(
            model=self._llm_model,
            messages=messages,
            temperature=self._temperature,
        )

        return RagAnswer(
            answer=response.content,
            sources=[
                RagSource(
                    source_path=result.chunk.source_path, chunk_id=result.chunk.id
                )
                for result in retrieved
            ],
            retrieved=retrieved,
            usage=response.usage,
            latency_ms=response.latency_ms,
        )


__all__ = [
    "DEFAULT_TEMPERATURE",
    "EMBED_BATCH_SIZE",
    "RagAnswer",
    "RagPipeline",
    "RagSource",
]
