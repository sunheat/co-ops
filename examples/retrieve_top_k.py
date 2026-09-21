"""Embed the sample corpus in memory and print the top-k chunks for a query.

Usage:
    # Configure an embedding provider in .env / environment (see .env.example), e.g.:
    #   EMBEDDING_PROVIDER=gemini
    #   EMBEDDING_MODEL=gemini-embedding-001
    uv run --env-file .env python -m examples.retrieve_top_k
    uv run --env-file .env python -m examples.retrieve_top_k "Where is margin calculated?"
"""

import sys

from packages.llm import embedding_client_from_env
from packages.rag import (
    InMemoryVectorStore,
    chunk_documents,
    load_code_files,
    load_markdown_docs,
    load_text_docs,
)

DEFAULT_QUERY = "Where is margin calculated?"
PREVIEW_CHARACTERS = 160
EMBED_BATCH_SIZE = 100  # Gemini rejects embedding batches above 100 inputs


def main() -> None:
    """Index the default corpus and show the chunks closest to one query."""
    query = " ".join(sys.argv[1:]) or DEFAULT_QUERY
    documents = [*load_markdown_docs(), *load_text_docs(), *load_code_files()]
    chunks = chunk_documents(documents)
    client, model = embedding_client_from_env()

    index_vectors: list[list[float]] = []
    index_tokens = 0
    index_latency_ms = 0.0
    with client:
        for start in range(0, len(chunks), EMBED_BATCH_SIZE):
            response = client.embed(
                [chunk.content for chunk in chunks[start : start + EMBED_BATCH_SIZE]],
                model=model,
            )
            index_vectors.extend(response.embeddings)
            index_tokens += response.usage.total_tokens if response.usage else 0
            index_latency_ms += response.latency_ms or 0.0
        query_response = client.embed(query, model=model)

    store = InMemoryVectorStore()
    for chunk, vector in zip(chunks, index_vectors, strict=True):
        store.add(chunk, vector)

    results = store.search(query_response.embeddings[0])

    print(f"model:     {query_response.model}")
    print(f"chunks:    {len(store)} (dimension {query_response.dimension})")
    print(f"query:     {query}")
    print(f"\nTop {len(results)} chunks:")
    for rank, result in enumerate(results, start=1):
        chunk = result.chunk
        preview = " ".join(chunk.content.split())
        if len(preview) > PREVIEW_CHARACTERS:
            preview = f"{preview[:PREVIEW_CHARACTERS]}..."
        print(
            f"\n{rank}. score {result.score:.4f}  {chunk.id}\n"
            f"   source: {chunk.source_path} [{chunk.start_char}:{chunk.end_char}] "
            f"type={chunk.metadata['source_type']}\n"
            f"   {preview}"
        )

    if index_tokens:
        print(f"\ntokens:    {index_tokens} (index)")
    print(f"index:     {index_latency_ms:.0f} ms")
    if query_response.latency_ms is not None:
        print(f"query:     {query_response.latency_ms:.0f} ms")


if __name__ == "__main__":
    main()
