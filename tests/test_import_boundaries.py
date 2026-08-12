"""Tests for importing the public application packages in a fresh process."""

import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[1]


def run_fresh_import(module_name: str, names: str) -> subprocess.CompletedProcess[str]:
    """Import one public package before any other project package is loaded."""
    return subprocess.run(
        [sys.executable, "-c", f"from {module_name} import {names}"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_prompt_package_is_importable_first():
    """The prompt application boundary works in a fresh interpreter."""
    result = run_fresh_import(
        "packages.prompt", "ContextBlock, MessageBuilder, PromptTemplate"
    )

    assert result.returncode == 0, result.stderr


def test_structured_output_package_is_importable_first():
    """The structured-output application boundary works in a fresh interpreter."""
    result = run_fresh_import(
        "packages.structured_output",
        "InvestigationPlan, parse_investigation_plan, request_investigation_plan",
    )

    assert result.returncode == 0, result.stderr


def test_llm_root_preserves_legacy_application_exports():
    """Legacy package-root imports still work in a fresh interpreter."""
    result = run_fresh_import(
        "packages.llm",
        "ContextBlock, ContextBuilder, InvestigationPlan, MessageBuilder, "
        "PromptTemplate, parse_investigation_plan",
    )

    assert result.returncode == 0, result.stderr
