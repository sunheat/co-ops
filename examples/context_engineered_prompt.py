"""Build a context-engineered prompt using four explicit context layers."""

import json

from packages.context import ContextBuilder, RetrievedChunk
from packages.prompt import ContextBlock, MessageBuilder


def main() -> None:
    """Print a provider-ready message payload backed by mocked retrieval."""
    context = ContextBuilder(
        retrieved_chunks=[
            RetrievedChunk(
                source="runbook.md",
                content=(
                    "Reconciliation failures can result from delayed trade imports."
                ),
            ),
            RetrievedChunk(
                source="incident-102.md",
                content="The mismatch appeared after the overnight batch job.",
            ),
        ]
    ).build(
        system_context=(
            "You are an enterprise support assistant. Base conclusions on the "
            "provided evidence and state uncertainty."
        ),
        memory_context=(
            "The user prefers concise diagnoses with actionable verification steps."
        ),
        task_context="Investigate the margin mismatch for client ACME-102.",
    )

    evidence = [
        ContextBlock(label=chunk["source"], content=chunk["content"])
        for chunk in context["retrieved_context"]
    ]
    evidence.append(ContextBlock(label="Memory", content=context["memory_context"]))
    messages = MessageBuilder().build(
        system=context["system_context"],
        context=evidence,
        task=context["task_context"],
        output_instruction=(
            "Return JSON with likely_causes, supporting_sources, and next_steps."
        ),
    )

    print(json.dumps([message.to_dict() for message in messages], indent=2))


if __name__ == "__main__":
    main()
