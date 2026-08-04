"""Structured JSON output schemas and validation helpers."""

import json
from typing import Literal

from pydantic import BaseModel, ValidationError

from .client import LLMClient
from .schemas import ChatMessage


class InvestigationPlan(BaseModel):
    """A validated investigation plan returned by an LLM."""

    summary: str
    likely_causes: list[str]
    evidence: list[str]
    next_steps: list[str]
    confidence: Literal["low", "medium", "high"]


def investigation_plan_output_instruction() -> str:
    """Return an instruction that asks the LLM for schema-conforming JSON."""
    schema = json.dumps(InvestigationPlan.model_json_schema(), indent=2)
    return (
        "Return only a valid JSON object with no Markdown fences or extra text. "
        "It must conform to this JSON Schema:\n"
        f"{schema}"
    )


def parse_investigation_plan(response_text: str) -> InvestigationPlan:
    """Parse LLM JSON output and validate it as an ``InvestigationPlan``.

    Invalid JSON raises ``ValueError``. JSON that does not match the schema
    raises Pydantic's ``ValidationError``.
    """
    if not isinstance(response_text, str):
        raise TypeError("response_text must be a string")

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response is not valid JSON") from exc

    return InvestigationPlan.model_validate(payload)


def investigation_plan_correction_instruction(error: Exception) -> str:
    """Return an instruction for correcting invalid investigation-plan output."""
    schema = json.dumps(InvestigationPlan.model_json_schema(), indent=2)
    return (
        "Your previous response could not be parsed or did not match the required "
        "schema. Return a corrected response as only a valid JSON object, with no "
        "Markdown fences or extra text.\n"
        f"Validation error: {error}\n"
        "It must conform to this JSON Schema:\n"
        f"{schema}"
    )


def request_investigation_plan(
    client: LLMClient,
    model: str,
    messages: list[ChatMessage | dict],
    **chat_kwargs: object,
) -> InvestigationPlan:
    """Request an investigation plan and retry once with a correction prompt.

    The correction retry is only used for invalid model output. Provider and
    transport errors continue to be handled by ``LLMClient.chat``.
    """
    response = client.chat(
        model=model,
        messages=messages,
        response_format="json",
        **chat_kwargs,
    )
    try:
        return parse_investigation_plan(response.content)
    except (ValueError, ValidationError) as error:
        correction_messages = [
            *messages,
            ChatMessage(role="assistant", content=response.content),
            ChatMessage(
                role="user",
                content=investigation_plan_correction_instruction(error),
            ),
        ]
        corrected_response = client.chat(
            model=model,
            messages=correction_messages,
            response_format="json",
            **chat_kwargs,
        )
        return parse_investigation_plan(corrected_response.content)
