"""Load repository documents into a shared RAG document schema."""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Literal

SourceType = Literal["doc", "code", "ticket", "runbook"]

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DOCS_ROOT = REPOSITORY_ROOT / "data" / "sample_docs"
DEFAULT_CODE_ROOT = REPOSITORY_ROOT / "data" / "sample_codebase"

MARKDOWN_SUFFIXES = frozenset({".md", ".markdown"})
TEXT_SUFFIXES = frozenset({".txt"})
CODE_LANGUAGES = {
    ".c": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cs": "csharp",
    ".go": "go",
    ".h": "c",
    ".hpp": "cpp",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".php": "php",
    ".ps1": "powershell",
    ".py": "python",
    ".rb": "ruby",
    ".rs": "rust",
    ".scala": "scala",
    ".sh": "shell",
    ".ts": "typescript",
    ".tsx": "typescript",
}


@dataclass(frozen=True)
class Document:
    """A source file normalized for later chunking and retrieval."""

    id: str
    source_path: str
    source_type: SourceType
    content: str
    metadata: dict[str, object] = field(default_factory=dict)


def load_markdown_docs(
    root: str | Path = DEFAULT_DOCS_ROOT,
) -> list[Document]:
    """Recursively load Markdown files from ``root`` in stable path order."""
    return _load_files(
        root,
        suffixes=MARKDOWN_SUFFIXES,
        source_type_for_path=_document_source_type,
        metadata_for_path=lambda path: {
            "extension": path.suffix.lower(),
            "format": "markdown",
        },
    )


def load_text_docs(root: str | Path = DEFAULT_DOCS_ROOT) -> list[Document]:
    """Recursively load plain-text files from ``root`` in stable path order."""
    return _load_files(
        root,
        suffixes=TEXT_SUFFIXES,
        source_type_for_path=_document_source_type,
        metadata_for_path=lambda path: {
            "extension": path.suffix.lower(),
            "format": "text",
        },
    )


def load_code_files(root: str | Path = DEFAULT_CODE_ROOT) -> list[Document]:
    """Recursively load supported source-code files from ``root``."""
    return _load_files(
        root,
        suffixes=CODE_LANGUAGES,
        source_type_for_path=lambda _path, _root: "code",
        metadata_for_path=lambda path: {
            "extension": path.suffix.lower(),
            "language": CODE_LANGUAGES[path.suffix.lower()],
        },
    )


def _load_files(
    root: str | Path,
    *,
    suffixes: Collection[str],
    source_type_for_path: Callable[[Path, Path], SourceType],
    metadata_for_path: Callable[[Path], dict[str, object]],
) -> list[Document]:
    source_root = _validated_directory(root)
    documents = []

    for path in _matching_files(source_root, suffixes):
        source_path = _source_path(path, source_root)
        documents.append(
            Document(
                id=_document_id(source_path),
                source_path=source_path,
                source_type=source_type_for_path(path, source_root),
                content=path.read_text(encoding="utf-8-sig"),
                metadata=metadata_for_path(path),
            )
        )

    return documents


def _validated_directory(root: str | Path) -> Path:
    path = Path(root).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Document root does not exist: {path}")
    if not path.is_dir():
        raise NotADirectoryError(f"Document root is not a directory: {path}")
    return path


def _matching_files(root: Path, suffixes: Collection[str]) -> list[Path]:
    normalized_suffixes = {suffix.lower() for suffix in suffixes}
    matches = (
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in normalized_suffixes
    )
    return sorted(
        matches,
        key=lambda path: (
            path.relative_to(root).as_posix().casefold(),
            path.relative_to(root).as_posix(),
        ),
    )


def _source_path(path: Path, root: Path) -> str:
    try:
        relative_path = path.relative_to(REPOSITORY_ROOT)
    except ValueError:
        relative_path = path.relative_to(root)
    return relative_path.as_posix()


def _document_id(source_path: str) -> str:
    digest = sha256(source_path.encode("utf-8")).hexdigest()
    return f"doc-{digest}"


def _document_source_type(path: Path, root: Path) -> SourceType:
    path_with_root = path.relative_to(root.parent)
    parent_names = {part.casefold() for part in path_with_root.parent.parts}
    if "tickets" in parent_names:
        return "ticket"
    if "runbooks" in parent_names:
        return "runbook"
    return "doc"


__all__ = [
    "CODE_LANGUAGES",
    "DEFAULT_CODE_ROOT",
    "DEFAULT_DOCS_ROOT",
    "Document",
    "SourceType",
    "load_code_files",
    "load_markdown_docs",
    "load_text_docs",
]
