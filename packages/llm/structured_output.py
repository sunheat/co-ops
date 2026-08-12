"""Backward-compatible import path for the structured output package."""

from packages.structured_output import (
    InvestigationPlan,
    investigation_plan_correction_instruction,
    investigation_plan_output_instruction,
    parse_investigation_plan,
    request_investigation_plan,
)

__all__ = [
    "InvestigationPlan",
    "investigation_plan_correction_instruction",
    "investigation_plan_output_instruction",
    "parse_investigation_plan",
    "request_investigation_plan",
]
