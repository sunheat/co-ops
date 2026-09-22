"""Answer one question with the in-memory RAG pipeline from scratch.

Usage:
    # Configure embedding and chat providers in .env / environment
    # (see .env.example), e.g.:
    #   EMBEDDING_PROVIDER=gemini
    #   EMBEDDING_MODEL=gemini-embedding-001
    #   LLM_PROVIDER=openai
    #   LLM_MODEL=gpt-4o-mini
    uv run --env-file .env python -m examples.ask_rag
    uv run --env-file .env python -m examples.ask_rag "Where is margin calculated?"
"""

import sys

from packages.llm import chat_client_from_env, embedding_client_from_env
from packages.rag import (
    RagPipeline,
    chunk_documents,
    load_code_files,
    load_markdown_docs,
    load_text_docs,
)

DEFAULT_QUESTION = "Where is margin calculated?"
PREVIEW_CHARACTERS = 160


def main() -> None:
    """Index the sample corpus in memory and print one cited answer."""
    question = " ".join(sys.argv[1:]) or DEFAULT_QUESTION
    chunks = chunk_documents(
        [*load_markdown_docs(), *load_text_docs(), *load_code_files()]
    )
    embedding_client, embedding_model = embedding_client_from_env()
    llm_client, llm_model = chat_client_from_env()

    with embedding_client, llm_client:
        pipeline = RagPipeline(
            embedding_client=embedding_client,
            embedding_model=embedding_model,
            llm_client=llm_client,
            llm_model=llm_model,
        )
        pipeline.index(chunks)
        answer = pipeline.ask(question)

    print(f"embedding: {embedding_model}")
    print(f"chat:      {llm_model}")
    print(f"chunks:    {pipeline.chunk_count}")
    print(f"question:  {question}")

    print(f"\nAnswer:\n{answer.answer}")

    print("\nSources:")
    for source in answer.sources:
        print(f"  {source.source_path} ({source.chunk_id})")

    print("\nRetrieved chunks:")
    for rank, result in enumerate(answer.retrieved, start=1):
        chunk = result.chunk
        preview = " ".join(chunk.content.split())
        if len(preview) > PREVIEW_CHARACTERS:
            preview = f"{preview[:PREVIEW_CHARACTERS]}..."
        print(
            f"{rank}. score {result.score:.4f}  {chunk.id}\n"
            f"   source: {chunk.source_path} [{chunk.start_char}:{chunk.end_char}] "
            f"type={chunk.metadata['source_type']}\n"
            f"   {preview}"
        )

    print("\nToken usage:")
    if answer.usage is not None:
        print(
            f"  prompt {answer.usage.prompt_tokens}, "
            f"completion {answer.usage.completion_tokens}, "
            f"total {answer.usage.total_tokens}"
        )
    else:
        print("  not reported by the provider")
    if answer.latency_ms is not None:
        print(f"  latency {answer.latency_ms:.0f} ms")


if __name__ == "__main__":
    main()
