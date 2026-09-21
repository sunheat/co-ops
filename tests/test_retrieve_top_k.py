"""Tests for the in-memory retrieval example's indexing path."""

import json
import sys

import httpx

from examples import retrieve_top_k
from packages.llm import EmbeddingClient
from packages.rag import (
    chunk_documents,
    load_code_files,
    load_markdown_docs,
    load_text_docs,
)

DIMENSION = 2


def _client_with_constant_vectors(call_sizes: list[int]) -> EmbeddingClient:
    """Return a client whose transport echoes one constant vector per input."""

    def handler(request):
        inputs = json.loads(request.content)["input"]
        call_sizes.append(len(inputs))
        return httpx.Response(
            200,
            json={
                "model": "test-embed",
                "data": [
                    {"index": index, "embedding": [1.0, 0.0]}
                    for index in range(len(inputs))
                ],
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
            },
        )

    client = EmbeddingClient(base_url="http://testserver/v1")
    client._client.close()
    client._client = httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
        timeout=client.timeout,
    )
    return client


def test_main_indexes_in_batches_and_prints_ranked_chunks(monkeypatch, capsys):
    """The example embeds the corpus in provider-sized batches and prints top-k."""
    call_sizes: list[int] = []
    chunk_count = len(
        chunk_documents([*load_markdown_docs(), *load_text_docs(), *load_code_files()])
    )
    monkeypatch.setattr(sys, "argv", ["retrieve_top_k"])
    monkeypatch.setattr(
        retrieve_top_k,
        "embedding_client_from_env",
        lambda: (_client_with_constant_vectors(call_sizes), "test-embed"),
    )

    retrieve_top_k.main()

    output = capsys.readouterr().out
    batch_sizes = [
        min(retrieve_top_k.EMBED_BATCH_SIZE, chunk_count - start)
        for start in range(0, chunk_count, retrieve_top_k.EMBED_BATCH_SIZE)
    ]
    assert call_sizes == [*batch_sizes, 1]  # the final call embeds the query
    assert all(size <= retrieve_top_k.EMBED_BATCH_SIZE for size in call_sizes)
    assert f"chunks:    {chunk_count} (dimension {DIMENSION})" in output
    assert f"query:     {retrieve_top_k.DEFAULT_QUERY}" in output
    assert "Top 5 chunks:" in output
    assert output.count("score 1.0000") == 5


def test_main_embeds_a_query_from_the_command_line(monkeypatch, capsys):
    """A query argument replaces the default question."""
    monkeypatch.setattr(sys, "argv", ["retrieve_top_k", "Which table stores margin?"])
    monkeypatch.setattr(
        retrieve_top_k,
        "embedding_client_from_env",
        lambda: (_client_with_constant_vectors([]), "test-embed"),
    )

    retrieve_top_k.main()

    assert "query:     Which table stores margin?" in capsys.readouterr().out
