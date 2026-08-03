"""Tests for structured LLM output parsing and Pydantic validation."""

import json

import pytest
from pydantic import ValidationError

from packages.llm.structured_output import (
    InvestigationPlan,
    investigation_plan_output_instruction,
    parse_investigation_plan,
)


def valid_plan_payload() -> dict[str, object]:
    """Return the smallest valid investigation-plan fixture."""
    return {
        "summary": "Delayed imports may explain the mismatch.",
        "likely_causes": ["The import job completed late."],
        "evidence": ["The runbook describes delayed imports."],
        "next_steps": ["Review the import job logs."],
        "confidence": "medium",
    }


def test_parse_investigation_plan_returns_validated_model():
    """Valid JSON is parsed into the typed Pydantic model."""
    plan = parse_investigation_plan(json.dumps(valid_plan_payload()))

    assert isinstance(plan, InvestigationPlan)
    assert plan.confidence == "medium"
    assert plan.next_steps == ["Review the import job logs."]


def test_parse_investigation_plan_rejects_invalid_json():
    """Malformed model output fails during JSON parsing."""
    with pytest.raises(ValueError, match="not valid JSON"):
        parse_investigation_plan('{"summary": "missing closing brace"')


def test_parse_investigation_plan_rejects_missing_required_field():
    """Pydantic rejects JSON that omits a required schema field."""
    payload = valid_plan_payload()
    del payload["next_steps"]

    with pytest.raises(ValidationError, match="next_steps"):
        parse_investigation_plan(json.dumps(payload))


def test_parse_investigation_plan_rejects_invalid_confidence_value():
    """The confidence field is constrained to the allowed literal values."""
    payload = valid_plan_payload()
    payload["confidence"] = "certain"

    with pytest.raises(ValidationError, match="confidence"):
        parse_investigation_plan(json.dumps(payload))


def test_output_instruction_contains_the_generated_json_schema():
    """Prompt instructions expose the same schema used for validation."""
    instruction = investigation_plan_output_instruction()

    assert "Return only a valid JSON object" in instruction
    assert '"summary"' in instruction
    assert '"confidence"' in instruction
