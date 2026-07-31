"""Build a context-aware message payload without calling an LLM provider."""

import json

from packages.llm.prompt import ContextBlock, MessageBuilder, PromptTemplate


def main() -> None:
    """Render a task and print the resulting Chat Completions messages."""
    template = PromptTemplate("Find likely causes for issue: {issue}.")
    messages = MessageBuilder().build(
        system="You are an enterprise support AI assistant.",
        developer_instruction="Use only the supplied context as evidence.",
        task=template.render(issue="Margin result mismatch for client ACME-102"),
        context=[
            ContextBlock(
                label="runbook.md",
                content="Reconciliation failures can result from delayed trade imports.",
            ),
            ContextBlock(
                label="ticket-102",
                content="The mismatch appeared after the overnight batch job.",
            ),
        ],
        output_instruction="Return JSON with likely_causes and next_steps.",
    )
    print(json.dumps([message.to_dict() for message in messages], indent=2))


if __name__ == "__main__":
    main()
