"""Application-layer prompt templates and provider-compatible messages."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from string import Formatter

from packages.llm.schemas import ChatMessage


@dataclass(frozen=True)
class PromptTemplate:
    """A small named-placeholder template for reusable prompt text.

    The template uses Python ``str.format`` syntax. Literal braces must be
    escaped as ``{{`` and ``}}``.
    """

    template: str

    def render(self, **values: object) -> str:
        """Render the template, rejecting missing or unexpected values."""
        field_names = self._field_names(self.template)
        missing = field_names.difference(values)
        unexpected = set(values).difference(field_names)
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"Missing template values: {names}")
        if unexpected:
            names = ", ".join(sorted(unexpected))
            raise ValueError(f"Unexpected template values: {names}")
        try:
            return self.template.format(**values)
        except (IndexError, KeyError, ValueError) as exc:
            raise ValueError(f"Invalid prompt template: {exc}") from exc

    @classmethod
    def _field_names(cls, template: str) -> set[str]:
        """Collect top-level fields, including nested fields in format specs."""
        field_names = set()
        for _, field_name, format_spec, _ in Formatter().parse(template):
            if field_name:
                field_names.add(cls._top_level_field_name(field_name))
            if format_spec:
                field_names.update(cls._field_names(format_spec))
        return field_names

    @staticmethod
    def _top_level_field_name(field_name: str) -> str:
        """Return the keyword argument name used by a replacement field."""
        return field_name.split(".", maxsplit=1)[0].split("[", maxsplit=1)[0]


@dataclass(frozen=True)
class ContextBlock:
    """A labeled context item included in a user task message."""

    content: str
    label: str | None = None


class MessageBuilder:
    """Build consistently ordered, provider-compatible chat messages."""

    def build(
        self,
        *,
        system: str,
        task: str,
        developer_instruction: str | None = None,
        context: str
        | Sequence[str | ContextBlock | Mapping[str, object]]
        | None = None,
        output_instruction: str | None = None,
    ) -> list[ChatMessage]:
        """Build portable system and user messages for a task.

        Developer instructions are folded into the system message because the
        gateway's portable role set does not include ``developer``. Context,
        task, and output instructions are combined into one user message so
        they remain one coherent request payload.
        """
        system_content = self._required(system, "system")
        if developer_instruction is not None:
            system_content = (
                f"{system_content}\n\nDeveloper instruction:\n"
                f"{self._required(developer_instruction, 'developer_instruction')}"
            )
        messages = [ChatMessage(role="system", content=system_content)]

        user_parts: list[str] = []
        rendered_context = self._render_context(context)
        if rendered_context:
            user_parts.append(f"Context:\n{rendered_context}")
        user_parts.append(f"Task:\n{self._required(task, 'task')}")
        if output_instruction is not None:
            user_parts.append(
                "Output instruction:\n"
                f"{self._required(output_instruction, 'output_instruction')}"
            )
        messages.append(ChatMessage(role="user", content="\n\n".join(user_parts)))
        return messages

    @staticmethod
    def _required(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be a non-empty string")
        return value

    def _render_context(
        self,
        context: str | Sequence[str | ContextBlock | Mapping[str, object]] | None,
    ) -> str:
        if context is None:
            return ""
        if isinstance(context, str):
            context = [context]

        blocks = []
        for index, item in enumerate(context, start=1):
            block = self._coerce_context_block(item)
            content = self._required(block.content, f"context[{index}].content")
            label = block.label.strip() if block.label is not None else ""
            if not label:
                label = f"Context {index}"
            blocks.append(f"[{label}]\n{content}")
        return "\n\n".join(blocks)

    @staticmethod
    def _coerce_context_block(
        item: str | ContextBlock | Mapping[str, object],
    ) -> ContextBlock:
        if isinstance(item, ContextBlock):
            return item
        if isinstance(item, str):
            return ContextBlock(content=item)
        if isinstance(item, Mapping):
            content = item.get("content")
            label = item.get("label")
            if not isinstance(content, str):
                raise TypeError("context mapping must contain a string 'content'")
            if label is not None and not isinstance(label, str):
                raise TypeError("context mapping 'label' must be a string")
            return ContextBlock(content=content, label=label)
        raise ValueError(
            "context items must be strings, ContextBlock objects, or mappings"
        )


__all__ = ["ContextBlock", "MessageBuilder", "PromptTemplate"]
