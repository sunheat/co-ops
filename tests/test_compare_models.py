"""Tests for the provider-observation script's probe decisions."""

import pytest

from examples.compare_models import _should_probe_errors
from packages.llm import APIError, LLMConnectionError, LLMTimeoutError


@pytest.mark.parametrize(
    "error",
    [
        LLMConnectionError("connection refused"),
        LLMTimeoutError("request timed out"),
    ],
)
def test_transport_failures_skip_the_bad_model_probe(error):
    assert not _should_probe_errors(error)


def test_model_specific_http_error_still_runs_the_probe():
    assert _should_probe_errors(APIError("model not found", status_code=404))
