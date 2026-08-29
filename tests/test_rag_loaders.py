"""Tests for loading RAG source files into the shared document schema."""

from pathlib import Path

import pytest

from packages.rag import (
    Document,
    load_code_files,
    load_markdown_docs,
    load_text_docs,
)

REPOSITORY_ROOT = Path(__file__).parents[1]


def test_default_markdown_loader_preserves_citation_paths_and_source_types():
    """Default corpus paths match the source paths used by evaluation cases."""
    documents = load_markdown_docs()
    by_path = {document.source_path: document for document in documents}

    architecture_path = "data/sample_docs/architecture.md"
    runbook_path = "data/sample_docs/runbooks/rb-margin-result-mismatch.md"
    ticket_path = "data/sample_docs/tickets/TKT-2024-001.md"
    incident_path = "data/sample_docs/tickets/incidents/INC-2024-001.md"

    assert by_path[architecture_path].source_type == "doc"
    assert by_path[runbook_path].source_type == "runbook"
    assert by_path[ticket_path].source_type == "ticket"
    assert by_path[incident_path].source_type == "ticket"
    assert "# ACFS Architecture Overview" in by_path[architecture_path].content


def test_nested_corpus_root_preserves_category_source_types():
    """Loading below a category directory keeps ticket and runbook types."""
    incident_documents = load_markdown_docs(
        REPOSITORY_ROOT / "data" / "sample_docs" / "tickets" / "incidents"
    )
    assert incident_documents
    assert all(document.source_type == "ticket" for document in incident_documents)

    runbook_documents = load_markdown_docs(
        REPOSITORY_ROOT / "data" / "sample_docs" / "runbooks"
    )
    assert runbook_documents
    assert all(document.source_type == "runbook" for document in runbook_documents)


def test_nested_external_root_preserves_category_source_types(tmp_path: Path):
    """Roots outside the repository still classify from retained ancestors."""
    ticket_directory = tmp_path / "tickets" / "incidents"
    ticket_directory.mkdir(parents=True)
    (ticket_directory / "INC-1.md").write_text("# Incident\n", encoding="utf-8")

    documents = load_markdown_docs(ticket_directory)

    assert [document.source_type for document in documents] == ["ticket"]


def test_markdown_loader_is_recursive_deterministic_and_ignores_other_files(
    tmp_path: Path,
):
    """Repeated loads return only Markdown documents in stable path order."""
    (tmp_path / "runbooks").mkdir()
    (tmp_path / "z.md").write_text("# Zed\n", encoding="utf-8")
    (tmp_path / "runbooks" / "A.MARKDOWN").write_text("# Runbook\n", encoding="utf-8")
    (tmp_path / "ignored.txt").write_text("Not Markdown\n", encoding="utf-8")

    first_load = load_markdown_docs(tmp_path)
    second_load = load_markdown_docs(tmp_path)

    assert [document.source_path for document in first_load] == [
        "runbooks/A.MARKDOWN",
        "z.md",
    ]
    assert first_load == second_load
    assert first_load[0].source_type == "runbook"
    assert first_load[0].metadata == {
        "extension": ".markdown",
        "format": "markdown",
    }


def test_text_loader_loads_plain_text_and_classifies_ticket(tmp_path: Path):
    """Plain-text tickets use the same normalized schema as Markdown files."""
    ticket_directory = tmp_path / "tickets"
    ticket_directory.mkdir()
    source = ticket_directory / "TKT-1.TXT"
    source.write_text("Support case\n", encoding="utf-8")
    (ticket_directory / "ignored.md").write_text("# Markdown\n", encoding="utf-8")

    documents = load_text_docs(tmp_path)

    assert documents == [
        Document(
            id=documents[0].id,
            source_path="tickets/TKT-1.TXT",
            source_type="ticket",
            content="Support case\n",
            metadata={"extension": ".txt", "format": "text"},
        )
    ]


def test_code_loader_adds_language_metadata_and_ignores_non_code(tmp_path: Path):
    """Supported source files are tagged as code with their language."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Example.java").write_text(
        "class Example {}\n", encoding="utf-8"
    )
    (tmp_path / "tool.PY").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Example\n", encoding="utf-8")

    documents = load_code_files(tmp_path)

    assert [document.source_path for document in documents] == [
        "src/Example.java",
        "tool.PY",
    ]
    assert all(document.source_type == "code" for document in documents)
    assert [document.metadata["language"] for document in documents] == [
        "java",
        "python",
    ]


def test_default_code_loader_uses_repository_relative_paths():
    """Loaded Java paths align with the committed evaluation source paths."""
    documents = load_code_files()

    expected_path = (
        "data/sample_codebase/java/margin-service/src/main/java/com/acme/acfs/"
        "margin/service/MarginCalculator.java"
    )
    assert expected_path in {document.source_path for document in documents}
    assert all(document.source_type == "code" for document in documents)


def test_document_ids_are_unique_and_stable_for_source_paths(tmp_path: Path):
    """A source path receives the same ID across loads and no sibling collision."""
    (tmp_path / "one.md").write_text("Same content\n", encoding="utf-8")
    (tmp_path / "two.md").write_text("Same content\n", encoding="utf-8")

    first_load = load_markdown_docs(tmp_path)
    second_load = load_markdown_docs(tmp_path)

    assert [document.id for document in first_load] == [
        document.id for document in second_load
    ]
    assert len({document.id for document in first_load}) == 2


@pytest.mark.parametrize(
    "loader", [load_markdown_docs, load_text_docs, load_code_files]
)
def test_loaders_reject_missing_roots(loader, tmp_path: Path):
    """A bad corpus path fails explicitly instead of returning an empty index."""
    missing_root = tmp_path / "missing"

    with pytest.raises(FileNotFoundError, match="Document root does not exist"):
        loader(missing_root)


@pytest.mark.parametrize(
    "loader", [load_markdown_docs, load_text_docs, load_code_files]
)
def test_loaders_reject_file_roots(loader, tmp_path: Path):
    """Loader roots must be directories so recursive behavior is unambiguous."""
    file_root = tmp_path / "document.md"
    file_root.write_text("# Not a directory\n", encoding="utf-8")

    with pytest.raises(NotADirectoryError, match="Document root is not a directory"):
        loader(file_root)


def test_repository_root_constant_matches_test_checkout():
    """The checked-in corpus used by default exists in this checkout."""
    assert (REPOSITORY_ROOT / "data" / "sample_docs").is_dir()
