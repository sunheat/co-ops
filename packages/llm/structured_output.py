"""Structured JSON output schemas and validation helpers."""

import json
from typing import Literal

from pydantic import BaseModel


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
