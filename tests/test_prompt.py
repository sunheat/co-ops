"""Tests for prompt templates and message construction."""

import pytest

from packages.llm import ChatMessage
from packages.prompt import ContextBlock, MessageBuilder, PromptTemplate


def test_prompt_template_renders_named_values():
    """PromptTemplate renders reusable named placeholders."""
    template = PromptTemplate("Investigate {issue} for {client}.")

    assert template.render(issue="margin mismatch", client="ACME-102") == (
        "Investigate margin mismatch for ACME-102."
    )


def test_prompt_template_rejects_missing_and_unexpected_values():
    """Template mistakes fail before an LLM call is made."""
    template = PromptTemplate("Investigate {issue}.")

    with pytest.raises(ValueError, match="Missing template values: issue"):
        template.render()
    with pytest.raises(ValueError, match="Unexpected template values: client"):
        template.render(issue="mismatch", client="ACME-102")


def test_prompt_template_supports_nested_format_spec_fields():
    """Nested format-spec fields are accepted as required template values."""
    template = PromptTemplate("{{width}} {value:{width}.{precision}f}")

    assert template.render(value=3.14159, width=8, precision=2) == "{width}     3.14"


def test_prompt_template_reports_missing_nested_format_spec_fields():
    """Missing nested format-spec fields use the normal missing-values error."""
    template = PromptTemplate("{value:{width}}")

    with pytest.raises(ValueError, match="Missing template values: width"):
        template.render(value="x")


def test_message_builder_orders_all_supported_message_sections():
    """The builder uses portable roles while retaining each instruction layer."""
    messages = MessageBuilder().build(
        system="You are a support assistant.",
        developer_instruction="Use evidence only.",
        task="Find likely causes.",
        context=[
            ContextBlock(label="runbook.md", content="Check delayed imports."),
            {"label": "ticket-102", "content": "Mismatch after batch."},
        ],
        output_instruction="Return JSON.",
    )

    assert messages == [
        ChatMessage(
            role="system",
            content=(
                "You are a support assistant.\n\n"
                "Developer instruction:\nUse evidence only."
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                "Context:\n[runbook.md]\nCheck delayed imports.\n\n"
                "[ticket-102]\nMismatch after batch.\n\n"
                "Task:\nFind likely causes.\n\n"
                "Output instruction:\nReturn JSON."
            ),
        ),
    ]


def test_message_builder_accepts_a_task_without_optional_sections():
    """A basic system-plus-task request needs no context or developer message."""
    messages = MessageBuilder().build(
        system="You are helpful.",
        task="Explain RAG.",
    )

    assert [message.role for message in messages] == ["system", "user"]
    assert messages[-1].content == "Task:\nExplain RAG."


def test_message_builder_uses_default_label_for_whitespace_context_label():
    """Whitespace-only context labels fall back to a readable default."""
    messages = MessageBuilder().build(
        system="You are helpful.",
        task="Explain RAG.",
        context=[ContextBlock(label="   ", content="RAG retrieves relevant sources.")],
    )

    assert messages[-1].content == (
        "Context:\n[Context 1]\nRAG retrieves relevant sources.\n\nTask:\nExplain RAG."
    )


def test_message_builder_treats_a_top_level_context_string_as_one_block():
    """A context string is one block rather than a sequence of characters."""
    messages = MessageBuilder().build(
        system="You are helpful.",
        task="Explain RAG.",
        context="RAG retrieves relevant sources.",
    )

    assert messages[-1].content == (
        "Context:\n[Context 1]\nRAG retrieves relevant sources.\n\nTask:\nExplain RAG."
    )


def test_message_builder_preserves_significant_context_whitespace():
    """Whitespace-sensitive context such as code keeps its original indentation."""
    code = "    def calculate_margin():\n        return 1"
    messages = MessageBuilder().build(
        system="You are helpful.",
        task="Explain this code.",
        context=[code],
    )

    assert messages[-1].content == (
        "Context:\n[Context 1]\n"
        "    def calculate_margin():\n        return 1\n\n"
        "Task:\nExplain this code."
    )


def test_message_builder_rejects_invalid_context_content():
    """Malformed context is rejected before it can produce an ambiguous prompt."""
    with pytest.raises(TypeError, match="context mapping must contain"):
        MessageBuilder().build(
            system="You are helpful.",
            task="Explain RAG.",
            context=[{"label": "broken"}],
        )
