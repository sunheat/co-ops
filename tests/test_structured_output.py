"""Tests for structured LLM output parsing and Pydantic validation."""

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from packages.llm.structured_output import (
    InvestigationPlan,
    investigation_plan_correction_instruction,
    investigation_plan_output_instruction,
    parse_investigation_plan,
    request_investigation_plan,
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


class ScriptedClient:
    """Minimal LLM client double that returns preconfigured response content."""

    def __init__(self, outputs: list[object]):
        self.outputs = outputs
        self.calls: list[dict[str, object]] = []

    def chat(self, *, model: str, messages: list, **kwargs):
        self.calls.append(
            {"model": model, "messages": list(messages), "kwargs": kwargs}
        )
        return SimpleNamespace(content=self.outputs.pop(0))


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


def test_request_investigation_plan_returns_first_valid_response_without_retry():
    """Schema-conforming output is returned without sending a correction request."""
    client = ScriptedClient([json.dumps(valid_plan_payload())])
    messages = [{"role": "user", "content": "Investigate the incident."}]

    plan = request_investigation_plan(client, "test-model", messages)

    assert plan.summary == "Delayed imports may explain the mismatch."
    assert len(client.calls) == 1
    assert client.calls[0]["kwargs"] == {"response_format": "json"}


def test_request_investigation_plan_includes_schema_in_initial_request():
    """The initial request states the schema before the model generates output."""
    client = ScriptedClient([json.dumps(valid_plan_payload())])
    messages = [{"role": "user", "content": "Investigate the incident."}]

    request_investigation_plan(client, "test-model", messages)

    initial_messages = client.calls[0]["messages"]
    assert len(initial_messages) == 2
    assert initial_messages[-1].content == investigation_plan_output_instruction()
    assert messages == [{"role": "user", "content": "Investigate the incident."}]


def test_request_investigation_plan_accepts_json_response_format_kwarg():
    """A forwarded JSON response-format option does not duplicate the keyword."""
    client = ScriptedClient([json.dumps(valid_plan_payload())])

    plan = request_investigation_plan(
        client,
        "test-model",
        [{"role": "user", "content": "Investigate the incident."}],
        response_format="json",
    )

    assert plan.confidence == "medium"
    assert len(client.calls) == 1
    assert client.calls[0]["kwargs"] == {"response_format": "json"}


def test_request_investigation_plan_rejects_non_json_response_format():
    """The structured-output helper cannot be configured to request text."""
    client = ScriptedClient([])

    with pytest.raises(ValueError, match="requires response_format='json'"):
        request_investigation_plan(
            client,
            "test-model",
            [{"role": "user", "content": "Investigate the incident."}],
            response_format="text",
        )

    assert client.calls == []


def test_request_investigation_plan_retries_invalid_json_with_correction_prompt():
    """Malformed JSON triggers one correction request before validation succeeds."""
    invalid_output = '{"summary": "missing closing brace"'
    client = ScriptedClient([invalid_output, json.dumps(valid_plan_payload())])
    messages = [{"role": "user", "content": "Investigate the incident."}]

    plan = request_investigation_plan(client, "test-model", messages)

    correction_messages = client.calls[1]["messages"]
    assert plan.confidence == "medium"
    assert len(client.calls) == 2
    assert correction_messages[-2].content == invalid_output
    assert "LLM response is not valid JSON" in correction_messages[-1].content


def test_request_investigation_plan_retries_non_string_response_content():
    """Non-string provider content is retried as invalid structured output."""
    invalid_output = {"summary": "not a JSON string"}
    client = ScriptedClient([invalid_output, json.dumps(valid_plan_payload())])

    plan = request_investigation_plan(
        client,
        "test-model",
        [{"role": "user", "content": "Investigate the incident."}],
    )

    correction_messages = client.calls[1]["messages"]
    assert plan.confidence == "medium"
    assert len(client.calls) == 2
    assert correction_messages[-2].content == json.dumps(invalid_output)
    assert "response_text must be a string" in correction_messages[-1].content


def test_request_investigation_plan_retries_missing_field_with_correction_prompt():
    """A Pydantic validation error triggers one correction request."""
    incomplete_payload = valid_plan_payload()
    del incomplete_payload["next_steps"]
    client = ScriptedClient([json.dumps(incomplete_payload), json.dumps(valid_plan_payload())])

    plan = request_investigation_plan(
        client,
        "test-model",
        [{"role": "user", "content": "Investigate the incident."}],
    )

    correction_messages = client.calls[1]["messages"]
    assert plan.next_steps == ["Review the import job logs."]
    assert len(client.calls) == 2
    assert "next_steps" in correction_messages[-1].content


def test_request_investigation_plan_raises_second_validation_failure():
    """The final validation error is raised after the single correction retry."""
    missing_field = valid_plan_payload()
    del missing_field["next_steps"]
    invalid_confidence = valid_plan_payload()
    invalid_confidence["confidence"] = "certain"
    client = ScriptedClient([json.dumps(missing_field), json.dumps(invalid_confidence)])

    with pytest.raises(ValidationError, match="confidence"):
        request_investigation_plan(
            client,
            "test-model",
            [{"role": "user", "content": "Investigate the incident."}],
        )

    assert len(client.calls) == 2


def test_correction_instruction_contains_error_and_schema():
    """Correction prompts identify the failure and restate the expected schema."""
    instruction = investigation_plan_correction_instruction(ValueError("bad JSON"))

    assert "Validation error: bad JSON" in instruction
    assert '"next_steps"' in instruction
