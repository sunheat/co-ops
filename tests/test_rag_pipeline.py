"""Tests for the minimal RAG pipeline and its example script."""

import json
import sys

import httpx
import pytest

from examples import ask_rag
from packages.llm import EmbeddingClient, LLMClient
from packages.rag import Chunk, RagPipeline
from packages.rag import rag_pipeline as rag_pipeline_module

CHAT_ANSWER = "Margin is calculated in MarginCalculator."
QUESTION = "Where is margin calculated?"

MARGIN_PATH = (
    "data/sample_codebase/java/margin-service/src/main/java/"
    "com/acme/acfs/margin/service/MarginCalculator.java"
)
RUNBOOK_PATH = "data/sample_docs/runbooks/rb-margin-result-mismatch.md"
FAQ_PATH = "data/sample_docs/faq.md"

MARGIN_CONTENT = "Margin is calculated in MarginCalculator."
RUNBOOK_CONTENT = "A margin result mismatch often starts with a delayed trade import."
FAQ_CONTENT = "The support desk answers questions during Sydney business hours."


def make_chunk(chunk_id: str, source_path: str, content: str) -> Chunk:
    """Build a chunk with a stable test identity."""
    return Chunk(
        id=chunk_id,
        document_id=f"doc-{chunk_id}",
        source_path=source_path,
        content=content,
        start_char=0,
        end_char=len(content),
        metadata={"source_type": "doc"},
    )


def margin_chunks() -> list[Chunk]:
    """Three chunks whose vectors rank margin first, runbook second, faq last."""
    return [
        make_chunk("chunk-margin", MARGIN_PATH, MARGIN_CONTENT),
        make_chunk("chunk-runbook", RUNBOOK_PATH, RUNBOOK_CONTENT),
        make_chunk("chunk-faq", FAQ_PATH, FAQ_CONTENT),
    ]


def margin_vectors() -> dict[str, list[float]]:
    """Deterministic embedding vectors for the margin corpus and question."""
    return {
        QUESTION: [1.0, 0.0],
        MARGIN_CONTENT: [1.0, 0.0],
        RUNBOOK_CONTENT: [0.9, 0.1],
        FAQ_CONTENT: [0.0, 1.0],
    }


def make_clients(
    vector_by_text: dict[str, list[float]] | None = None,
    chat_payloads: list[dict] | None = None,
    embed_call_sizes: list[int] | None = None,
) -> tuple[EmbeddingClient, LLMClient]:
    """Build embedding and chat clients backed by one mocked transport.

    Unknown texts embed to a constant vector, so examples that index the real
    corpus still run without a per-text vector table.
    """
    vectors = vector_by_text or {}

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        if request.url.path.endswith("/embeddings"):
            inputs = payload["input"]
            if embed_call_sizes is not None:
                embed_call_sizes.append(len(inputs))
            return httpx.Response(
                200,
                json={
                    "model": "test-embed",
                    "data": [
                        {"index": index, "embedding": vectors.get(text, [1.0, 0.0])}
                        for index, text in enumerate(inputs)
                    ],
                    "usage": {
                        "prompt_tokens": len(inputs),
                        "total_tokens": len(inputs),
                    },
                },
            )

        if chat_payloads is not None:
            chat_payloads.append(payload)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "model": "test-chat",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": CHAT_ANSWER},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            },
        )

    transport = httpx.MockTransport(handler)
    embedding_client = EmbeddingClient(base_url="http://testserver/v1")
    chat_client = LLMClient(base_url="http://testserver/v1", provider="test")
    for client in (embedding_client, chat_client):
        client._client.close()
        client._client = httpx.Client(
            base_url=client.base_url,
            transport=transport,
            timeout=client.timeout,
        )
    return embedding_client, chat_client


def make_pipeline(
    embedding_client: EmbeddingClient,
    chat_client: LLMClient,
) -> RagPipeline:
    """Build a pipeline wired to the two test clients."""
    return RagPipeline(
        embedding_client=embedding_client,
        embedding_model="test-embed",
        llm_client=chat_client,
        llm_model="test-chat",
    )


def test_ask_returns_answer_with_sources_from_retrieved_chunks():
    """The answer reports the ranked hits and their chunk-level sources."""
    embedding_client, chat_client = make_clients(margin_vectors())
    pipeline = make_pipeline(embedding_client, chat_client)
    pipeline.index(margin_chunks())

    answer = pipeline.ask(QUESTION)

    assert answer.answer == CHAT_ANSWER
    expected_ids = ["chunk-margin", "chunk-runbook", "chunk-faq"]
    assert [result.chunk.id for result in answer.retrieved] == expected_ids
    assert [source.chunk_id for source in answer.sources] == expected_ids
    assert [source.source_path for source in answer.sources] == [
        MARGIN_PATH,
        RUNBOOK_PATH,
        FAQ_PATH,
    ]
    assert answer.usage is not None
    assert answer.usage.total_tokens == 15
    assert answer.latency_ms is not None


def test_ask_sends_labeled_context_and_question_to_the_chat_model():
    """The chat request carries every retrieved chunk as labeled context."""
    chat_payloads: list[dict] = []
    embedding_client, chat_client = make_clients(margin_vectors(), chat_payloads)
    pipeline = make_pipeline(embedding_client, chat_client)
    pipeline.index(margin_chunks())

    pipeline.ask(QUESTION)

    payload = chat_payloads[0]
    assert payload["model"] == "test-chat"
    assert payload["temperature"] == rag_pipeline_module.DEFAULT_TEMPERATURE
    system_message, user_message = payload["messages"]
    assert system_message["role"] == "system"
    assert system_message["content"] == rag_pipeline_module.SYSTEM_PROMPT
    assert f"[{MARGIN_PATH}]" in user_message["content"]
    assert MARGIN_CONTENT in user_message["content"]
    assert QUESTION in user_message["content"]


def test_index_embeds_chunks_in_provider_sized_batches(monkeypatch):
    """Indexing requests embeddings in batches of EMBED_BATCH_SIZE."""
    monkeypatch.setattr(rag_pipeline_module, "EMBED_BATCH_SIZE", 2)
    embed_call_sizes: list[int] = []
    embedding_client, chat_client = make_clients(embed_call_sizes=embed_call_sizes)
    pipeline = make_pipeline(embedding_client, chat_client)
    chunks = [
        make_chunk(f"chunk-{index}", f"docs/{index}.md", f"content {index}")
        for index in range(5)
    ]

    pipeline.index(chunks)

    assert embed_call_sizes == [2, 2, 1]
    assert pipeline.chunk_count == 5


def test_ask_rejects_a_blank_question():
    """A question without text fails before any provider call."""
    embedding_client, chat_client = make_clients()
    pipeline = make_pipeline(embedding_client, chat_client)

    with pytest.raises(ValueError, match="question"):
        pipeline.ask("   ")


def test_ask_rag_example_prints_answer_sources_and_usage(monkeypatch, capsys):
    """The example indexes the sample corpus and prints every answer block."""
    embedding_client, chat_client = make_clients()

    monkeypatch.setattr(sys, "argv", ["ask_rag"])
    monkeypatch.setattr(
        ask_rag,
        "embedding_client_from_env",
        lambda: (embedding_client, "test-embed"),
    )
    monkeypatch.setattr(
        ask_rag,
        "chat_client_from_env",
        lambda: (chat_client, "test-chat"),
    )

    ask_rag.main()

    output = capsys.readouterr().out
    assert f"question:  {ask_rag.DEFAULT_QUESTION}" in output
    assert f"\nAnswer:\n{CHAT_ANSWER}" in output
    assert "\nSources:" in output
    assert "\nRetrieved chunks:" in output
    assert "\nToken usage:" in output
    assert "total 15" in output
