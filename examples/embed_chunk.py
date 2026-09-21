"""Embed one corpus chunk and report the vector dimension.

Usage:
    # Configure a provider in .env / environment (see .env.example), e.g.:
    #   EMBEDDING_PROVIDER=gemini
    #   EMBEDDING_MODEL=gemini-embedding-001
    uv run --env-file .env python -m examples.embed_chunk
"""

from packages.llm import embedding_client_from_env
from packages.rag import chunk_documents, load_markdown_docs

PREVIEW_VALUES = 4


def main() -> None:
    """Embed the first markdown chunk and print its vector details."""
    chunk = chunk_documents(load_markdown_docs())[0]
    client, model = embedding_client_from_env()

    with client:
        response = client.embed(chunk.content, model=model)

    preview = ", ".join(
        f"{value:.5f}" for value in response.embeddings[0][:PREVIEW_VALUES]
    )
    print(f"chunk:     {chunk.id}")
    print(f"source:    {chunk.source_path} [{chunk.start_char}:{chunk.end_char}]")
    print(f"model:     {response.model}")
    print(f"dimension: {response.dimension}")
    print(f"vector:    [{preview}, ...]")
    if response.usage is not None:
        print(f"tokens:    {response.usage.total_tokens}")
    if response.latency_ms is not None:
        print(f"latency:   {response.latency_ms:.0f} ms")
    print(f"attempts:  {response.attempts}")


if __name__ == "__main__":
    main()
