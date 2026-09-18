"""Chunk the sample corpus and print chunk counts with sample chunks."""

from packages.rag import (
    chunk_documents,
    chunk_statistics,
    load_code_files,
    load_markdown_docs,
    load_text_docs,
)

SAMPLE_CHUNK_LIMIT = 3
PREVIEW_CHARACTERS = 160


def main() -> None:
    """Index the default corpus and show representative chunks."""
    documents = [*load_markdown_docs(), *load_text_docs(), *load_code_files()]
    chunks = chunk_documents(documents)
    statistics = chunk_statistics(chunks)

    print(f"documents: {len(documents)}")
    print(f"chunks: {statistics['chunk_count']}")
    print(f"indexed documents: {statistics['document_count']}")
    print(f"characters: {statistics['total_characters']}")

    print("\nSample chunks:")
    for chunk in chunks[:SAMPLE_CHUNK_LIMIT]:
        preview = " ".join(chunk.content.split())
        if len(preview) > PREVIEW_CHARACTERS:
            preview = f"{preview[:PREVIEW_CHARACTERS]}..."
        print(
            f"\n{chunk.id}\n  source: {chunk.source_path} "
            f"[{chunk.start_char}:{chunk.end_char}] "
            f"index={chunk.metadata['chunk_index']}\n  {preview}"
        )


if __name__ == "__main__":
    main()
