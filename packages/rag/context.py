"""Four-layer context construction for retrieval-augmented prompts."""

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import TypedDict


@dataclass(frozen=True)
class RetrievedChunk:
    """A retrieved piece of evidence and the source it came from."""

    source: str
    content: str


class RetrievedContext(TypedDict):
    """JSON-serializable representation of a retrieved chunk."""

    source: str
    content: str


class BuiltContext(TypedDict):
    """The four context layers consumed by a context-engineered prompt."""

    system_context: str
    retrieved_context: list[RetrievedContext]
    memory_context: str
    task_context: str


DEFAULT_MOCK_RETRIEVED_CHUNKS = (
    RetrievedChunk(
        source="runbook.md",
        content="Reconciliation failures can result from delayed trade imports.",
    ),
)


class ContextBuilder:
    """Build a validated, JSON-serializable four-layer context payload.

    Retrieval is intentionally mocked for now. Callers can supply mock chunks to
    the constructor for a scenario, or rely on the representative default.
    """

    def __init__(
        self,
        retrieved_chunks: Iterable[RetrievedChunk | Mapping[str, object]] | None = None,
    ) -> None:
        chunks = (
            DEFAULT_MOCK_RETRIEVED_CHUNKS
            if retrieved_chunks is None
            else retrieved_chunks
        )
        self._retrieved_chunks = tuple(
            self._coerce_chunk(chunk, index)
            for index, chunk in enumerate(chunks, start=1)
        )

    def build(
        self,
        *,
        system_context: str,
        memory_context: str,
        task_context: str,
    ) -> BuiltContext:
        """Return the four context layers in stable prompt assembly order."""
        return {
            "system_context": self._required(system_context, "system_context"),
            "retrieved_context": [
                RetrievedContext(**asdict(chunk)) for chunk in self._retrieved_chunks
            ],
            "memory_context": self._required(memory_context, "memory_context"),
            "task_context": self._required(task_context, "task_context"),
        }

    @staticmethod
    def _required(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value

    @classmethod
    def _coerce_chunk(
        cls,
        chunk: RetrievedChunk | Mapping[str, object],
        index: int,
    ) -> RetrievedChunk:
        if isinstance(chunk, RetrievedChunk):
            source = chunk.source
            content = chunk.content
        elif isinstance(chunk, Mapping):
            source = chunk.get("source")
            content = chunk.get("content")
        else:
            raise TypeError(
                "retrieved chunks must be RetrievedChunk objects or mappings"
            )

        return RetrievedChunk(
            source=cls._required(source, f"retrieved_chunks[{index}].source"),
            content=cls._required(content, f"retrieved_chunks[{index}].content"),
        )
