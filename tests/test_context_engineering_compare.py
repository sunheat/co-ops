"""Adversarial offline tests for the prompt-quality benchmark."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import examples.context_engineering_compare as benchmark
from examples.context_engineering_compare import (
    ARTIFACT_SCHEMA,
    CASES,
    PROMPT_STYLES,
    BenchmarkResult,
    RunConfig,
    _initial_manifest,
    _legacy_case_01_correct,
    _prepare_artifact_directory,
    _regrade_artifact,
    _request_catalog,
    _result_from_response,
    _sha256_file,
    _update_manifest_from_results,
    _write_jsonl,
    _write_manifest,
    build_messages,
    main,
    parse_output,
    regrade_results,
    render_summary,
    validate_matrix,
    validate_request_catalog,
)
from packages.llm import LLMError, Usage

FIXTURE_DIRECTORY = (
    Path(__file__).parent / "fixtures" / "context_engineering_compare" / "live-v3"
)


def make_response(
    case,
    answer,
    evidence=None,
    *,
    finish_reason="stop",
    actual_model="test-model",
    usage=None,
    latency_ms=10.0,
    estimated_cost_usd=None,
):
    if evidence is None:
        evidence = sorted(case.required_sources)
    return SimpleNamespace(
        content=json.dumps({"answer": answer, "evidence": evidence}),
        usage=usage,
        estimated_cost_usd=estimated_cost_usd,
        latency_ms=latency_ms,
        attempts=1,
        id="response-id",
        model=actual_model,
        finish_reason=finish_reason,
    )


def score(case, answer, evidence=None, **kwargs):
    return _result_from_response(
        case,
        "structured",
        1,
        make_response(case, answer, evidence, **kwargs),
    )


WRONG_VALUES = {
    ("01_delayed_import", "reconciliation_started_at"): "2025-03-07T01:59:00Z",
    ("01_delayed_import", "trade_import_completed_at"): "2025-03-07T02:17:00Z",
    ("01_delayed_import", "cause"): "other",
    ("02_release_gate", "deployable_now"): True,
    ("02_release_gate", "blocking_condition"): "none",
    ("03_budget_math", "additional_spend_usd"): "39.99",
    ("04_api_timeline", "change"): "other",
    ("04_api_timeline", "failure_mechanism"): "other",
    ("05_identity_policy", "approved"): True,
    ("05_identity_policy", "submitted_document"): "passport",
    ("05_identity_policy", "policy_status"): "accepted",
    ("06_incident_severity", "severity"): "P2",
    ("07_feature_flag", "flag_name"): "OTHER_FLAG",
    ("07_feature_flag", "flag_value"): True,
    ("07_feature_flag", "effect"): "enabled",
    ("08_account_lock", "unlock_at"): "10:34:00Z",
    ("09_retention_date", "deletion_date"): "2025-03-11",
    ("10_shipping_rule", "shipping_charge_usd"): "7.00",
}


ANSWER_FIELDS = [
    (case, field_name)
    for case in CASES
    for field_name in case.answer_model.model_fields
    if field_name != "status"
]


def test_benchmark_has_ten_cases_and_three_styles():
    assert len(CASES) == 10
    assert PROMPT_STYLES == ("naive", "structured", "context_engineered")


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_every_exact_typed_answer_is_grounded(case):
    result = score(case, case.expected_answer)

    assert result.status == "ok"
    assert result.format_valid
    assert result.answer_schema_valid
    assert result.answer_correct
    assert result.evidence_cited
    assert result.grounded


@pytest.mark.parametrize(
    ("case", "field_name"),
    ANSWER_FIELDS,
    ids=lambda value: value.case_id if hasattr(value, "case_id") else value,
)
def test_each_valid_but_wrong_field_fails_correctness(case, field_name):
    answer = dict(case.expected_answer)
    answer[field_name] = WRONG_VALUES[(case.case_id, field_name)]

    result = score(case, answer)

    assert result.answer_schema_valid
    assert not result.answer_correct
    assert not result.grounded


@pytest.mark.parametrize(
    ("case", "field_name"),
    ANSWER_FIELDS,
    ids=lambda value: value.case_id if hasattr(value, "case_id") else value,
)
@pytest.mark.parametrize("invalid_value", [None, [], {}])
def test_model_controlled_wrong_types_never_escape_scoring(
    case, field_name, invalid_value
):
    answer = dict(case.expected_answer)
    answer[field_name] = invalid_value

    result = score(case, answer)

    assert result.status == "ok"
    assert not result.answer_schema_valid
    assert not result.answer_correct


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_missing_extra_and_insufficient_answer_branches(case):
    field_name = next(name for name in case.answer_model.model_fields if name != "status")
    missing = dict(case.expected_answer)
    del missing[field_name]
    extra = {**case.expected_answer, "explanation": "not allowed"}

    assert not score(case, missing).answer_schema_valid
    assert not score(case, extra).answer_schema_valid

    insufficient = score(case, {"status": "insufficient_evidence"})
    assert insufficient.answer_schema_valid
    assert not insufficient.answer_correct
    assert not insufficient.grounded


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "-Infinity", "1e3"])
@pytest.mark.parametrize("case_index,field_name", [(2, "additional_spend_usd"), (9, "shipping_charge_usd")])
def test_decimal_contract_rejects_nonfinite_and_noncanonical_values(
    case_index, field_name, value
):
    case = CASES[case_index]
    answer = dict(case.expected_answer)
    answer[field_name] = value

    result = score(case, answer)

    assert not result.answer_schema_valid
    assert not result.answer_correct


def test_decimal_contract_rejects_unicode_digit_homoglyphs():
    case = CASES[2]
    answer = dict(case.expected_answer)
    answer["additional_spend_usd"] = "4٠.٠٠"

    assert not score(case, answer).answer_schema_valid


@pytest.mark.parametrize(
    "value",
    ["2025-02-30", "2025/03/12", "20250312", None, 20250312],
)
def test_date_contract_rejects_invalid_values_without_raising(value):
    case = CASES[8]
    answer = dict(case.expected_answer)
    answer["deletion_date"] = value

    assert not score(case, answer).answer_schema_valid


@pytest.mark.parametrize(
    "value",
    [
        None,
        123,
        {},
        "2025-03-07 02:00:00+00:00",
        "2025-03-07T02:00Z",
        "2025-03-07T02:00:00",
        "20250307T020000+0000",
    ],
)
def test_datetime_contract_rejects_wrong_types_and_non_rfc3339(value):
    case = CASES[0]
    answer = dict(case.expected_answer)
    answer["reconciliation_started_at"] = value

    assert not score(case, answer).answer_schema_valid


def test_case_01_compares_timezone_equivalent_instants():
    case = CASES[0]
    answer = dict(case.expected_answer)
    answer["reconciliation_started_at"] = "2025-03-07T03:00:00+01:00"
    answer["trade_import_completed_at"] = "2025-03-07T03:18:00+01:00"

    assert score(case, answer).answer_correct


@pytest.mark.parametrize(
    ("started", "completed"),
    [
        ("2025-03-07T02:18:00Z", "2025-03-07T02:00:00Z"),
        ("2025-03-07T02:00:00Z", "2025-03-07T02:00:00Z"),
    ],
)
def test_case_01_rejects_reversed_and_equal_instants(started, completed):
    case = CASES[0]
    answer = dict(case.expected_answer)
    answer["reconciliation_started_at"] = started
    answer["trade_import_completed_at"] = completed

    assert not score(case, answer).answer_correct


@pytest.mark.parametrize(
    "value", ["10:35Z", "103500Z", "10:35:00+00:00", "24:00:00Z", None]
)
def test_time_contract_requires_exact_valid_hh_mm_ss_z(value):
    case = CASES[7]
    answer = dict(case.expected_answer)
    answer["unlock_at"] = value

    assert not score(case, answer).answer_schema_valid


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_nonstandard_json_constants_are_rejected(constant):
    content = (
        '{"answer":{"status":"answered","additional_spend_usd":'
        f"{constant}" + '},"evidence":["budget_policy.md"]}'
    )

    parsed = parse_output(content, CASES[2])

    assert not parsed.format_valid
    assert parsed.raw_payload == content


@pytest.mark.parametrize(
    "content",
    [
        (
            '{"answer":{"status":"answered","additional_spend_usd":"0",'
            '"additional_spend_usd":"40.00"},'
            '"evidence":["budget_policy.md","march_ledger.md"]}'
        ),
        (
            '{"answer":{"status":"answered","additional_spend_usd":"0"},'
            '"answer":{"status":"answered","additional_spend_usd":"40.00"},'
            '"evidence":["budget_policy.md","march_ledger.md"]}'
        ),
    ],
)
def test_duplicate_json_members_are_rejected(content):
    parsed = parse_output(content, CASES[2])

    assert not parsed.format_valid
    assert parsed.raw_payload == content


def test_deeply_nested_json_is_a_format_failure_not_an_exception():
    content = "[" * 5000 + "0" + "]" * 5000

    parsed = parse_output(content, CASES[0])

    assert not parsed.format_valid
    assert parsed.raw_payload == content


def test_unpaired_surrogates_are_safely_persisted_as_json_escapes(tmp_path):
    case = CASES[2]
    content = (
        '{"answer":{"status":"answered","additional_spend_usd":"40.00"},'
        '"evidence":["budget_policy.md","march_ledger.md","\\ud800"]}'
    )
    response = SimpleNamespace(
        content=content,
        usage=None,
        estimated_cost_usd=None,
        latency_ms=1.0,
        attempts=1,
        id="id",
        model="model-\ud800",
        finish_reason="stop",
    )
    result = _result_from_response(
        case,
        "naive",
        1,
        response,
        request_id="id",
        request_hash="0" * 64,
    )

    benchmark._persist_results(tmp_path / "results.jsonl", [result])

    assert b"\\ud800" in (tmp_path / "results.jsonl").read_bytes()


@pytest.mark.parametrize(
    "value",
    [
        "0001-01-01T00:00:00+23:59",
        "9999-12-31T23:59:59-23:59",
        "2025-03-07T02:00:00.0000009Z",
    ],
)
def test_rfc3339_values_that_cannot_be_compared_exactly_are_rejected(value):
    case = CASES[0]
    answer = dict(case.expected_answer)
    answer["reconciliation_started_at"] = value

    result = score(case, answer)

    assert not result.answer_schema_valid
    assert not result.answer_correct


def test_pydantic_models_store_semantic_scalar_types():
    budget = CASES[2].answer_adapter.validate_python(CASES[2].expected_answer)
    delayed = CASES[0].answer_adapter.validate_python(CASES[0].expected_answer)
    retention = CASES[8].answer_adapter.validate_python(CASES[8].expected_answer)
    lock = CASES[7].answer_adapter.validate_python(CASES[7].expected_answer)

    assert isinstance(budget.additional_spend_usd, benchmark.Decimal)
    assert isinstance(delayed.reconciliation_started_at, datetime)
    assert isinstance(retention.deletion_date, benchmark.date)
    assert isinstance(lock.unlock_at, benchmark.datetime_time)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.case_id)
def test_citations_are_nonempty_unique_bare_known_and_complete(case):
    required = sorted(case.required_sources)
    assert score(case, case.expected_answer, required).grounded

    invalid_sets = [
        [],
        required[:-1],
        required + [required[0]],
        [f"[{required[0]}]", *required[1:]],
        [f" {required[0]}", *required[1:]],
        ["unknown.md", *required[1:]],
        [{"source": required[0]}, *required[1:]],
    ]
    for evidence in invalid_sets:
        result = score(case, case.expected_answer, evidence)
        assert not result.evidence_cited
        assert not result.grounded


def test_malformed_payload_is_preserved_for_audit():
    content = "not json"

    parsed = parse_output(content, CASES[0])

    assert not parsed.format_valid
    assert parsed.raw_payload == content


@pytest.mark.parametrize("finish_reason", ["length", "MAX_TOKENS", "Max_Output_Tokens"])
def test_truncated_response_is_not_gradable(finish_reason):
    case = CASES[0]

    result = score(case, case.expected_answer, finish_reason=finish_reason)

    assert result.status == "truncated"
    assert result.answer_correct is None
    assert result.grounded is None
    assert result.response


@pytest.mark.parametrize("finish_reason", ["content_filter", "SAFETY", "blocked"])
def test_filtered_response_is_a_non_gradable_provider_error(finish_reason):
    case = CASES[0]

    result = score(case, case.expected_answer, finish_reason=finish_reason)

    assert result.status == "provider_error"
    assert result.answer_correct is None
    assert result.grounded is None
    assert result.error.startswith("InvalidResponse:")


@pytest.mark.parametrize(
    ("finish_reason", "expected_status"),
    [
        ("RECITATION", "provider_error"),
        ("error", "provider_error"),
        ("cancelled", "provider_error"),
        ("content-filter", "provider_error"),
        ("MAX-TOKENS", "truncated"),
        ("max_length", "provider_error"),
        (None, "provider_error"),
        (123, "provider_error"),
    ],
)
def test_unknown_and_provider_failure_finish_reasons_fail_closed(
    finish_reason, expected_status
):
    result = score(CASES[0], CASES[0].expected_answer, finish_reason=finish_reason)

    assert result.status == expected_status
    assert result.grounded is None


def test_chat_response_without_choices_is_not_gradable():
    case = CASES[0]
    response = make_response(case, case.expected_answer)
    response.choices = []

    result = _result_from_response(case, "naive", 1, response)

    assert result.status == "provider_error"
    assert result.grounded is None


def test_response_metadata_is_bounded_and_cannot_overflow_cost():
    case = CASES[0]
    response = make_response(
        case,
        case.expected_answer,
        usage=Usage(10**400, 1, 10**400 + 1),
        latency_ms=-1,
        estimated_cost_usd=-1,
    )
    response.attempts = 0

    result = _result_from_response(
        case,
        "naive",
        1,
        response,
        input_price_per_million=1.0,
        output_price_per_million=1.0,
    )

    assert result.prompt_tokens is None
    assert result.estimated_cost_usd is None
    assert result.latency_ms is None
    assert result.attempts is None

    huge_latency = score(
        case,
        case.expected_answer,
        latency_ms=1e308,
        usage=Usage(10, 20, 30),
    )
    assert huge_latency.latency_ms is None


def test_provider_usage_can_include_unreported_reasoning_tokens():
    response = make_response(
        CASES[0], CASES[0].expected_answer, usage=Usage(19, 75, 933)
    )
    result = _result_from_response(
        CASES[0],
        "naive",
        1,
        response,
        input_price_per_million=1.0,
        output_price_per_million=1.0,
    )

    assert (result.prompt_tokens, result.completion_tokens, result.total_tokens) == (
        19,
        75,
        933,
    )
    assert result.estimated_cost_usd is None


def test_rfc3339_unknown_offset_marker_is_not_a_proven_instant():
    case = CASES[0]
    answer = dict(case.expected_answer)
    answer["reconciliation_started_at"] = "2025-03-07T02:00:00-00:00"

    assert not score(case, answer).answer_schema_valid


def test_all_prompt_styles_have_identical_contract_and_evidence():
    for case in CASES:
        schema = json.dumps(
            case.answer_model.model_json_schema(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        rendered = {
            style: "\n".join(message.content for message in build_messages(case, style))
            for style in PROMPT_STYLES
        }
        for content in rendered.values():
            assert schema in content
            for evidence in case.evidence:
                assert evidence.source in content
                assert evidence.content in content
            assert '{"status":"insufficient_evidence"}' in content
            assert "JSON booleans must be true or false, never quoted strings" in content
            assert "containing every provided source ID" in content

        schema_payload = case.answer_model.model_json_schema()
        for property_schema in schema_payload["properties"].values():
            if "pattern" in property_schema:
                assert property_schema["pattern"].startswith("^")
                assert property_schema["pattern"].endswith("$")
    assert (
        CASES[1].answer_model.model_json_schema()["properties"]["deployable_now"][
            "type"
        ]
        == "boolean"
    )


def test_request_order_is_reproducible_balanced_and_seeded():
    first = _request_catalog(2, seed=42)
    second = _request_catalog(2, seed=42)
    third = _request_catalog(2, seed=43)

    assert first == second
    assert [item["request_id"] for item in first] != [
        item["request_id"] for item in third
    ]
    assert {
        item["request_id"]: item["request_hash"] for item in first
    } == {item["request_id"]: item["request_hash"] for item in third}

    positions = {style: [] for style in PROMPT_STYLES}
    for index in range(0, len(first), len(PROMPT_STYLES)):
        for position, request in enumerate(first[index : index + 3]):
            positions[request["prompt_style"]].append(position)
    for style_positions in positions.values():
        counts = [style_positions.count(position) for position in range(3)]
        assert max(counts) - min(counts) <= 1


def test_partial_matrix_allows_sparse_repeat_ids():
    requests = _request_catalog(2, seed=7)
    repeat_two = next(request for request in requests if request["repeat"] == 2)

    matrix = validate_matrix([repeat_two], 2, allow_partial=True)

    assert matrix == {"planned": 60, "observed": 1, "missing": 59}
    with pytest.raises(ValueError, match="matrix mismatch"):
        validate_matrix([repeat_two], 2)


def test_matrix_rejects_duplicate_unknown_and_request_identity_mismatch():
    requests = _request_catalog(1)
    validate_matrix(requests, 1)
    with pytest.raises(ValueError, match="duplicate"):
        validate_matrix([*requests, requests[0]], 1)
    with pytest.raises(ValueError, match="unknown"):
        validate_matrix([{**requests[0], "case_id": "unknown"}], 1, allow_partial=True)
    record = {**requests[0], "request_hash": "tampered"}
    with pytest.raises(ValueError, match="identity"):
        validate_matrix([record], 1, allow_partial=True, requests=requests)


def test_jsonl_hash_uses_exact_lf_bytes(tmp_path):
    path = tmp_path / "records.jsonl"
    records = [{"value": 1}, {"value": "two"}]

    _write_jsonl(path, records)

    assert b"\r\n" not in path.read_bytes()
    assert _sha256_file(path) == benchmark._sha256_bytes(
        benchmark._jsonl_bytes(records)
    )


def make_config():
    return RunConfig(
        provider="test",
        requested_model="test-model",
        temperature=0.0,
        max_tokens=512,
        max_retries=0,
        request_delay_seconds=0.0,
        input_price_per_million=None,
        output_price_per_million=None,
    )


def build_artifact(
    root: Path,
    *,
    repeats=1,
    seed=3,
    selected=None,
    status=None,
):
    config = make_config()
    requests = _request_catalog(
        repeats,
        seed,
        provider=config.provider,
        model=config.requested_model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )
    if selected is None:
        selected = requests
    directory = root / f"source-{uuid_suffix(root)}"
    directory.mkdir()
    started_at = "2026-08-09T00:00:00+00:00"
    manifest = _initial_manifest(
        kind="synthetic",
        status="running",
        run_id="synthetic-run",
        started_at=started_at,
        config=config,
        repeats=repeats,
        seed=seed,
        requests=requests,
    )
    _prepare_artifact_directory(directory, requests, manifest)
    results = []
    for request in selected:
        case = benchmark.CASE_BY_ID[request["case_id"]]
        result = _result_from_response(
            case,
            request["prompt_style"],
            request["repeat"],
            make_response(
                case,
                case.expected_answer,
                usage=Usage(100, 20, 120),
                estimated_cost_usd=0.001,
            ),
            request_id=request["request_id"],
            request_hash=request["request_hash"],
        )
        results.append(result)
    _write_jsonl(directory / "results.jsonl", (asdict(result) for result in results))
    final_status = status or ("complete" if len(results) == len(requests) else "partial")
    completed_at = "2026-08-09T00:05:00+00:00"
    summary = render_summary(
        results,
        provider=config.provider,
        model=config.requested_model,
        repeats=repeats,
        generated_at=completed_at,
        allow_partial=final_status == "partial",
        report_kind="synthetic",
    )
    benchmark._atomic_write_text(directory / "summary.md", summary)
    manifest = _update_manifest_from_results(
        manifest,
        results,
        directory / "results.jsonl",
        status=final_status,
        completed_at=completed_at,
        summary_path=directory / "summary.md",
    )
    _write_manifest(directory / "manifest.json", manifest)
    return directory, requests, results, manifest


def uuid_suffix(root: Path) -> str:
    return str(len(list(root.iterdir())))


def test_request_catalog_validation_recomputes_all_invariants(tmp_path):
    _, requests, _, manifest = build_artifact(tmp_path)
    validate_request_catalog(requests, manifest)

    tampered = [dict(request) for request in requests]
    tampered[0] = {**tampered[0], "messages": [{"role": "user", "content": "changed"}]}
    with pytest.raises(ValueError, match="catalog"):
        validate_request_catalog(tampered, manifest)

    wrong_manifest = replace(manifest, rubric_version="old")
    with pytest.raises(ValueError, match="rubric"):
        validate_request_catalog(requests, wrong_manifest)


def test_manifest_strictly_rejects_boolean_integer_fields(tmp_path):
    directory, _, _, _ = build_artifact(tmp_path)
    payload = benchmark._read_json(directory / "manifest.json")
    payload["repeats"] = True

    with pytest.raises(ValueError, match="manifest shape"):
        benchmark._manifest_from_dict(payload)


def test_manifest_rejects_unanchored_hash_and_backward_terminal_time(tmp_path):
    directory, _, _, _ = build_artifact(tmp_path)
    payload = benchmark._read_json(directory / "manifest.json")
    payload["scorer_source_sha256"] = "x" + "0" * 64 + "y"
    with pytest.raises(ValueError, match="manifest shape"):
        benchmark._manifest_from_dict(payload)

    payload = benchmark._read_json(directory / "manifest.json")
    payload["completed_at"] = "2026-08-08T23:59:00Z"
    with pytest.raises(ValueError, match="manifest shape"):
        benchmark._manifest_from_dict(payload)


@pytest.mark.parametrize("mutation", ["crlf", "blank", "no-final-lf", "spaces"])
def test_source_results_must_use_canonical_jsonl_bytes(tmp_path, mutation):
    directory, _, _, _ = build_artifact(tmp_path)
    results_path = directory / "results.jsonl"
    content = results_path.read_bytes()
    if mutation == "crlf":
        changed = content.replace(b"\n", b"\r\n")
    elif mutation == "blank":
        changed = b"\n" + content
    elif mutation == "no-final-lf":
        changed = content.rstrip(b"\n")
    else:
        changed = content.replace(b'"actual_model":', b'"actual_model" :', 1)
    results_path.write_bytes(changed)
    manifest_path = directory / "manifest.json"
    payload = benchmark._read_json(manifest_path)
    payload["results_file_sha256"] = benchmark._sha256_bytes(changed)
    benchmark._atomic_write_bytes(
        manifest_path,
        json.dumps(payload, sort_keys=True, indent=2).encode() + b"\n",
    )

    with pytest.raises(ValueError, match="canonical|blank|LF"):
        _regrade_artifact(results_path, tmp_path, allow_partial=False)


def test_source_prompt_hash_is_verified(tmp_path):
    directory, _, _, _ = build_artifact(tmp_path)
    (directory / "prompts.md").write_text("tampered", encoding="utf-8")

    with pytest.raises(ValueError, match="prompt file hash"):
        _regrade_artifact(
            directory / "results.jsonl", tmp_path, allow_partial=False
        )


def test_source_prompt_must_be_derived_from_verified_requests(tmp_path):
    directory, _, _, _ = build_artifact(tmp_path)
    prompts_path = directory / "prompts.md"
    prompts_path.write_text("tampered", encoding="utf-8")
    manifest_path = directory / "manifest.json"
    payload = benchmark._read_json(manifest_path)
    payload["prompts_file_sha256"] = _sha256_file(prompts_path)
    benchmark._atomic_write_bytes(
        manifest_path,
        json.dumps(payload, sort_keys=True, indent=2).encode() + b"\n",
    )

    with pytest.raises(ValueError, match="verified requests"):
        _regrade_artifact(
            directory / "results.jsonl", tmp_path, allow_partial=False
        )


def test_source_manifest_and_summary_must_be_canonical_derivations(tmp_path):
    directory, _, _, _ = build_artifact(tmp_path)
    manifest_path = directory / "manifest.json"
    payload = benchmark._read_json(manifest_path)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="manifest is not canonical"):
        _regrade_artifact(
            directory / "results.jsonl", tmp_path, allow_partial=False
        )

    directory, _, _, _ = build_artifact(tmp_path)
    summary_path = directory / "summary.md"
    summary_path.write_text("# Incorrect 100% report\n", encoding="utf-8")
    manifest = benchmark._manifest_from_dict(
        benchmark._read_json(directory / "manifest.json")
    )
    manifest = replace(manifest, summary_file_sha256=_sha256_file(summary_path))
    _write_manifest(directory / "manifest.json", manifest)
    with pytest.raises(ValueError, match="not derived"):
        _regrade_artifact(
            directory / "results.jsonl", tmp_path, allow_partial=False
        )


def test_regrade_rejects_a_noncanonical_result_filename(tmp_path):
    directory, _, _, _ = build_artifact(tmp_path)
    alternate = directory / "alternate.jsonl"
    alternate.write_bytes((directory / "results.jsonl").read_bytes())
    output = tmp_path / "output"

    with pytest.raises(SystemExit) as error:
        main(
            [
                "--regrade-results",
                str(alternate),
                "--output-dir",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert not output.exists()


def test_regrade_rejects_case_changed_result_filename(tmp_path):
    directory, _, _, _ = build_artifact(tmp_path)
    changed_case = directory / "RESULTS.JSONL"
    changed_case.write_bytes((directory / "results.jsonl").read_bytes())

    with pytest.raises(SystemExit) as error:
        main(["--regrade-results", str(changed_case), "--output-dir", str(tmp_path / "out")])

    assert error.value.code == 2


def test_regrade_uses_manifest_repeats_and_preserves_partial_status(tmp_path):
    all_requests = _request_catalog(
        2,
        seed=3,
        provider="test",
        model="test-model",
    )
    repeat_one_only = [request for request in all_requests if request["repeat"] == 1]
    source, _, _, _ = build_artifact(
        tmp_path,
        repeats=2,
        selected=repeat_one_only,
        status="partial",
    )

    output = _regrade_artifact(
        source / "results.jsonl", tmp_path, allow_partial=True
    )
    output_manifest = benchmark._manifest_from_dict(
        benchmark._read_json(output / "manifest.json")
    )
    summary = (output / "summary.md").read_text(encoding="utf-8")

    assert output_manifest.repeats == 2
    assert output_manifest.status == "partial"
    assert output_manifest.planned_calls == 60
    assert "Planned calls: 60" in summary
    assert "missing calls: 30" in summary
    assert (output / "requests.jsonl").exists()


def test_regrade_accepts_sparse_repeat_two_and_is_chainable(tmp_path):
    all_requests = _request_catalog(
        2,
        seed=3,
        provider="test",
        model="test-model",
    )
    sparse = [next(request for request in all_requests if request["repeat"] == 2)]
    source, _, _, _ = build_artifact(
        tmp_path, repeats=2, selected=sparse, status="partial"
    )

    first = _regrade_artifact(source / "results.jsonl", tmp_path, allow_partial=True)
    second = _regrade_artifact(first / "results.jsonl", tmp_path, allow_partial=True)

    assert (first / "requests.jsonl").read_bytes() == (
        second / "requests.jsonl"
    ).read_bytes()
    assert (first / "summary.md").read_bytes() == (second / "summary.md").read_bytes()


def test_regrade_normalizes_stale_success_flags_on_error():
    case = CASES[0]
    record = asdict(
        BenchmarkResult(
            case_id=case.case_id,
            title=case.title,
            prompt_style="naive",
            repeat=1,
            request_id="id",
            request_hash="0" * 64,
            status="provider_error",
            format_valid=True,
            answer_schema_valid=True,
            evidence_cited=True,
            citations_valid=True,
            answer_correct=True,
            grounded=True,
            cited_sources=list(case.required_sources),
            prompt_tokens=None,
            completion_tokens=None,
            total_tokens=None,
            latency_ms=1.0,
            estimated_cost_usd=None,
            attempts=3,
            response_id=None,
            actual_model=None,
            finish_reason=None,
            response="",
            error="RateLimitError: busy",
        )
    )

    result = regrade_results([record])[0]

    assert result.status == "provider_error"
    assert result.answer_correct is None
    assert result.grounded is None
    assert result.attempts == 3


def test_regrade_rejects_malformed_provider_error_usage():
    case = CASES[0]
    record = asdict(
        benchmark._failure_result(
            case,
            "naive",
            1,
            LLMError("busy"),
            request_id="id",
            request_hash="0" * 64,
        )
    )
    record["prompt_tokens"] = 10

    with pytest.raises(ValueError, match="result record"):
        regrade_results([record])


def test_result_model_rejects_inconsistent_total_tokens():
    case = CASES[0]
    record = asdict(score(case, case.expected_answer, usage=Usage(10, 20, 30)))
    record["total_tokens"] = 5

    with pytest.raises(ValueError, match="result record"):
        regrade_results([record])


@pytest.mark.parametrize(
    ("status", "finish_reason"),
    [("truncated", "stop"), ("ok", "content_filter")],
)
def test_result_model_rejects_status_finish_reason_contradictions(
    status, finish_reason
):
    record = asdict(score(CASES[0], CASES[0].expected_answer))
    record["status"] = status
    record["finish_reason"] = finish_reason
    if status == "truncated":
        for field_name in (
            "format_valid",
            "answer_schema_valid",
            "evidence_cited",
            "citations_valid",
            "answer_correct",
            "grounded",
        ):
            record[field_name] = None

    with pytest.raises(ValueError, match="result record"):
        regrade_results([record])


def test_strict_persistence_model_rejects_stale_non_gradable_metrics():
    record = asdict(
        benchmark._failure_result(
            CASES[0],
            "naive",
            1,
            LLMError("failed"),
            request_id="id",
            request_hash="0" * 64,
        )
    )
    record["grounded"] = True

    with pytest.raises(benchmark.ValidationError):
        benchmark.BenchmarkResultPayload.model_validate(record, strict=True)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            (
                "Reconciliation started at 02:00 UTC and the trade import completed at "
                "02:18 UTC, causing the mismatch."
            ),
            True,
        ),
        (
            (
                "The trade import completed at 02:18 UTC; reconciliation started at "
                "02:00 UTC, causing the mismatch."
            ),
            True,
        ),
        (
            (
                "Trade import completed at 02:00 UTC and reconciliation started at "
                "02:18 UTC, causing the mismatch."
            ),
            False,
        ),
        (
            (
                "The alert opened at 01:00 UTC and closed at 01:30 UTC. "
                "Reconciliation started at 02:00 UTC and import completed at "
                "02:18 UTC, but the delayed import did not cause the mismatch."
            ),
            False,
        ),
        (
            (
                "Reconciliation started at 99:00 UTC and import completed at 99:18 "
                "UTC, causing the mismatch."
            ),
            False,
        ),
        (
            (
                "Reconciliation started at 2025-03-07T02:00:00Z and import completed "
                "at 2025-03-07T02:18:00Z, causing the mismatch."
            ),
            True,
        ),
        (
            (
                "Reconciliation started at 02:00 UTC and import completed at 02:18 "
                "UTC. A network outage caused the mismatch."
            ),
            False,
        ),
        (
            (
                "Reconciliation started at 02:00 UTC and import completed at 02:18 "
                "UTC. The most likely cause was not the delayed import."
            ),
            False,
        ),
        (
            (
                "Reconciliation started at 02:00 UTC and import completed at 02:18 "
                "UTC. There is no evidence that the import caused the mismatch."
            ),
            False,
        ),
        (
            (
                "Reconciliation started at 02:00 UTC and import completed at 02:18 "
                "UTC. The delayed import is not responsible for causing the mismatch."
            ),
            False,
        ),
        (
            (
                "Reconciliation started at 02:00 UTC and import completed at 02:18 "
                "UTC. The import failed to cause the mismatch."
            ),
            False,
        ),
        (
            (
                "Reconciliation started at 02:00 UTC and import completed at 02:18 "
                "UTC. The import was unrelated to what caused the mismatch."
            ),
            False,
        ),
        (
            (
                "Reconciliation started at 02:00 UTC and import completed at 02:18 "
                "UTC, but the delayed import didn't cause the mismatch."
            ),
            False,
        ),
        (
            (
                "Reconciliation started at 02:00 UTC and reconciliation started at "
                "02:01 UTC. Import completed at 02:18 UTC, causing the mismatch."
            ),
            False,
        ),
        (
            (
                "Reconciliation started at 02:00 UTC and import completed at 02:18 "
                "UTC. The import caused no mismatch."
            ),
            False,
        ),
        (
            (
                "Reconciliation started at 02:00 UTC and import completed at 02:18 "
                "UTC. The mismatch was caused by anything but the import."
            ),
            False,
        ),
        (
            (
                "Reconciliation started at 02:00 UTC and import completed at 02:18 "
                "UTC. The import could not have caused the mismatch."
            ),
            False,
        ),
        (
            (
                "Reconciliation started at 02:00 UTC and import completed at 02:18 "
                "UTC. It is false that the import caused the mismatch."
            ),
            False,
        ),
    ],
)
def test_legacy_case_01_binds_event_timestamps_and_causality(text, expected):
    assert _legacy_case_01_correct(text) is expected


def test_deep_legacy_json_cannot_abort_import_scoring():
    content = "[" * 5000 + "0" + "]" * 5000

    assert not _legacy_case_01_correct(content)


def test_summary_separates_gradable_coverage_and_actual_models():
    case = CASES[0]
    ok = score(
        case,
        case.expected_answer,
        actual_model="actual-a",
        usage=Usage(100, 20, 120),
    )
    truncated = score(
        case,
        case.expected_answer,
        finish_reason="length",
        actual_model="actual-b",
    )
    truncated.prompt_style = "naive"
    truncated.repeat = 2

    summary = render_summary(
        [ok, truncated],
        provider="test",
        model="router",
        repeats=2,
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
        allow_partial=True,
    )

    assert "**PARTIAL**" in summary
    assert "<code>actual-a</code>=1, <code>actual-b</code>=1" in summary
    assert "provider errors: 0; truncated: 1" in summary
    assert "coverage 1/20" in summary


def test_summary_escapes_model_metadata_and_rejects_cost_overflow():
    rows = []
    for repeat in range(1, 3):
        for case in CASES:
            result = score(
                case,
                case.expected_answer,
                actual_model="evil\n- Report: **COMPLETE**",
                estimated_cost_usd=1e308,
            )
            result.prompt_style = "naive"
            result.repeat = repeat
            rows.append(result)

    summary = render_summary(
        rows,
        provider="test",
        model="router",
        repeats=2,
        generated_at=datetime(2026, 8, 9, tzinfo=UTC),
        allow_partial=True,
    )

    assert "<code>evil\\u000a- Report: **COMPLETE**</code>" in summary
    assert "\n- Report: **COMPLETE**=20" not in summary
    assert summary.splitlines()[-1].endswith("n/a |")


@pytest.mark.parametrize(
    "argv",
    [
        ["--repeats", "0"],
        ["--max-tokens", "0"],
        ["--max-retries", "-1"],
        ["--temperature", "nan"],
        ["--temperature", "inf"],
        ["--temperature", "2.1"],
        ["--request-delay-seconds", "-1"],
        ["--input-price-per-million", "nan"],
    ],
)
def test_cli_rejects_invalid_numeric_inputs_without_artifacts(argv, tmp_path):
    with pytest.raises(SystemExit) as error:
        main([*argv, "--dry-run", "--output-dir", str(tmp_path)])

    assert error.value.code == 2
    assert not list(tmp_path.iterdir())


def test_cli_rejects_one_sided_pricing_without_artifacts(tmp_path):
    with pytest.raises(SystemExit) as error:
        main(
            [
                "--dry-run",
                "--input-price-per-million",
                "1",
                "--output-dir",
                str(tmp_path),
            ]
        )

    assert error.value.code == 2
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("flag", ["--provider", "--model"])
def test_cli_rejects_empty_provider_or_model_before_artifact(flag, tmp_path):
    with pytest.raises(SystemExit) as error:
        main(["--dry-run", flag, "", "--output-dir", str(tmp_path)])

    assert error.value.code == 2
    assert not list(tmp_path.iterdir())


def test_regrade_rejects_explicit_generation_options(tmp_path):
    source, _, _, _ = build_artifact(tmp_path)
    output = tmp_path / "output"

    with pytest.raises(SystemExit) as error:
        main(
            [
                "--regrade-results",
                str(source / "results.jsonl"),
                "--provider",
                "ignored",
                "--output-dir",
                str(output),
            ]
        )

    assert error.value.code == 2
    assert not output.exists()


def test_cli_disables_long_option_abbreviations():
    with pytest.raises(SystemExit) as error:
        benchmark.build_parser().parse_args(["--prov", "ignored"])

    assert error.value.code == 2


def test_dry_run_writes_self_consistent_unique_artifact(tmp_path):
    assert main(["--dry-run", "--seed", "9", "--output-dir", str(tmp_path)]) == 0
    assert main(["--dry-run", "--seed", "9", "--output-dir", str(tmp_path)]) == 0
    directories = sorted(tmp_path.iterdir())

    assert len(directories) == 2
    for directory in directories:
        manifest = benchmark._manifest_from_dict(
            benchmark._read_json(directory / "manifest.json")
        )
        requests = benchmark._read_jsonl(directory / "requests.jsonl")
        validate_request_catalog(requests, manifest)
        assert manifest.status == "dry_run"
        assert manifest.request_file_sha256 == _sha256_file(
            directory / "requests.jsonl"
        )


class FakeRouter:
    responses_before_interrupt = None

    def __init__(self, settings):
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def chat(self, name, messages, **kwargs):
        if (
            self.responses_before_interrupt is not None
            and self.calls >= self.responses_before_interrupt
        ):
            raise KeyboardInterrupt
        self.calls += 1
        user_text = messages[-1].content
        case = next(case for case in CASES if case.question in user_text)
        return make_response(
            case,
            case.expected_answer,
            usage=Usage(100, 20, 120),
        )


def test_live_run_flushes_results_and_completes(monkeypatch, tmp_path):
    monkeypatch.setattr(benchmark, "load_settings", lambda: SimpleNamespace(max_retries=0))
    monkeypatch.setattr(benchmark, "ModelRouter", FakeRouter)
    FakeRouter.responses_before_interrupt = None

    assert main(["--output-dir", str(tmp_path), "--seed", "4"]) == 0
    directory = next(tmp_path.iterdir())
    manifest = benchmark._manifest_from_dict(
        benchmark._read_json(directory / "manifest.json")
    )

    assert manifest.status == "complete"
    assert manifest.completed_calls == 30
    assert len(benchmark._read_jsonl(directory / "results.jsonl")) == 30


def test_live_interrupt_preserves_rows_and_marks_partial(monkeypatch, tmp_path):
    monkeypatch.setattr(benchmark, "load_settings", lambda: SimpleNamespace(max_retries=0))
    monkeypatch.setattr(benchmark, "ModelRouter", FakeRouter)
    FakeRouter.responses_before_interrupt = 2

    with pytest.raises(KeyboardInterrupt):
        main(["--output-dir", str(tmp_path), "--seed", "4"])
    directory = next(tmp_path.iterdir())
    manifest = benchmark._manifest_from_dict(
        benchmark._read_json(directory / "manifest.json")
    )

    assert manifest.status == "partial"
    assert manifest.completed_calls == 2
    assert manifest.interrupted_at is not None
    assert manifest.active_request_id is not None
    assert len(benchmark._read_jsonl(directory / "results.jsonl")) == 2


def test_settings_failure_marks_created_run_partial(monkeypatch, tmp_path):
    def fail_settings():
        raise RuntimeError("bad settings")

    monkeypatch.setattr(benchmark, "load_settings", fail_settings)

    with pytest.raises(RuntimeError, match="bad settings"):
        main(["--output-dir", str(tmp_path)])
    directory = next(tmp_path.iterdir())
    manifest = benchmark._manifest_from_dict(
        benchmark._read_json(directory / "manifest.json")
    )
    assert manifest.status == "partial"
    assert manifest.completed_calls == 0


def test_live_initialization_failure_does_not_publish_partial_directory(
    monkeypatch, tmp_path
):
    def fail_prepare(directory, requests, manifest):
        raise OSError("cannot initialize")

    monkeypatch.setattr(benchmark, "_prepare_artifact_directory", fail_prepare)

    with pytest.raises(OSError, match="cannot initialize"):
        main(["--output-dir", str(tmp_path)])

    assert not list(tmp_path.iterdir())


def test_post_publish_failure_marks_visible_run_partial(monkeypatch, tmp_path):
    original = benchmark._publish_staged_directory

    def publish_then_fail(staging, final):
        original(staging, final)
        raise OSError("failed after directory publish")

    monkeypatch.setattr(benchmark, "_publish_staged_directory", publish_then_fail)

    with pytest.raises(OSError, match="failed after directory publish"):
        main(["--output-dir", str(tmp_path)])
    directory = next(tmp_path.iterdir())
    manifest = benchmark._manifest_from_dict(
        benchmark._read_json(directory / "manifest.json")
    )
    assert manifest.status == "partial"
    assert manifest.completed_at is not None


def test_summary_failure_marks_completed_calls_partial(monkeypatch, tmp_path):
    monkeypatch.setattr(
        benchmark, "load_settings", lambda: SimpleNamespace(max_retries=0)
    )
    monkeypatch.setattr(benchmark, "ModelRouter", FakeRouter)
    FakeRouter.responses_before_interrupt = None

    def fail_summary(*args, **kwargs):
        raise RuntimeError("summary failed")

    monkeypatch.setattr(benchmark, "render_summary", fail_summary)
    with pytest.raises(RuntimeError, match="summary failed"):
        main(["--output-dir", str(tmp_path)])
    directory = next(tmp_path.iterdir())
    manifest = benchmark._manifest_from_dict(
        benchmark._read_json(directory / "manifest.json")
    )
    assert manifest.status == "partial"
    assert manifest.completed_calls == 30


def test_append_failure_does_not_increment_persisted_count(monkeypatch, tmp_path):
    monkeypatch.setattr(benchmark, "load_settings", lambda: SimpleNamespace(max_retries=0))
    monkeypatch.setattr(benchmark, "ModelRouter", FakeRouter)
    FakeRouter.responses_before_interrupt = None

    def fail_persist(path, records):
        raise OSError("disk full")

    monkeypatch.setattr(benchmark, "_persist_results", fail_persist)
    with pytest.raises(OSError, match="disk full"):
        main(["--output-dir", str(tmp_path)])
    directory = next(tmp_path.iterdir())
    manifest = benchmark._manifest_from_dict(
        benchmark._read_json(directory / "manifest.json")
    )
    assert manifest.status == "partial"
    assert manifest.completed_calls == 0
    assert not benchmark._read_jsonl(directory / "results.jsonl")


def test_post_commit_persist_failure_recovers_disk_row(monkeypatch, tmp_path):
    monkeypatch.setattr(
        benchmark, "load_settings", lambda: SimpleNamespace(max_retries=0)
    )
    monkeypatch.setattr(benchmark, "ModelRouter", FakeRouter)
    FakeRouter.responses_before_interrupt = None
    original = benchmark._persist_results

    def persist_then_fail(path, records):
        original(path, records)
        raise OSError("failed after replace")

    monkeypatch.setattr(benchmark, "_persist_results", persist_then_fail)
    with pytest.raises(OSError, match="failed after replace"):
        main(["--output-dir", str(tmp_path)])
    directory = next(tmp_path.iterdir())
    manifest = benchmark._manifest_from_dict(
        benchmark._read_json(directory / "manifest.json")
    )

    assert manifest.status == "partial"
    assert manifest.completed_calls == 1
    assert manifest.completed_at is not None
    assert manifest.active_request_id is None
    assert len(benchmark._read_jsonl(directory / "results.jsonl")) == 1


def test_provider_error_preserves_attempts_and_latency():
    case = CASES[0]
    error = LLMError("failed", attempts=3)
    error.latency_ms = 125.5

    result = benchmark._failure_result(
        case,
        "naive",
        1,
        error,
        request_id="id",
        request_hash="hash",
    )

    assert result.status == "provider_error"
    assert result.attempts == 3
    assert result.latency_ms == 125.5
    assert result.grounded is None


def test_legacy_import_does_not_fabricate_v2_requests(tmp_path):
    source = tmp_path / "legacy.jsonl"
    records = [
        {
            "case_id": "01_delayed_import",
            "prompt_style": "structured",
            "repeat": 2,
            "response": (
                "Reconciliation started at 02:00 UTC and import completed at "
                "02:18 UTC, causing the mismatch."
            ),
        }
    ]
    _write_jsonl(source, records)

    assert (
        main(
            [
                "--regrade-results",
                str(source),
                "--legacy-import",
                "--output-dir",
                str(tmp_path / "output"),
            ]
        )
        == 0
    )
    directory = next((tmp_path / "output").iterdir())
    manifest = benchmark._read_json(directory / "manifest.json")

    assert manifest["schema"] != ARTIFACT_SCHEMA
    assert manifest["request_provenance"] == "unavailable"
    assert not (directory / "requests.jsonl").exists()
    assert manifest["observed_repeats"] == [2]
    assert manifest["importer_version"] == benchmark.LEGACY_IMPORTER_VERSION
    assert manifest["observed_matrix"] == [
        {
            "case_id": "01_delayed_import",
            "prompt_style": "structured",
            "repeat": 2,
        }
    ]


def test_committed_live_fixture_is_complete_and_exactly_regradable(tmp_path):
    if not (FIXTURE_DIRECTORY / "manifest.json").exists():
        pytest.skip("authoritative fixture is generated only after the live-run gate")
    source_bytes = {
        path.name: path.read_bytes() for path in FIXTURE_DIRECTORY.iterdir()
    }

    snapshot = benchmark._validate_source_artifact(
        FIXTURE_DIRECTORY, allow_partial=False
    )
    output = _regrade_artifact(
        FIXTURE_DIRECTORY / "results.jsonl", tmp_path, allow_partial=False
    )

    assert snapshot.matrix == {"planned": 60, "observed": 60, "missing": 0}
    assert snapshot.manifest.status == "complete"
    assert (output / "summary.md").read_bytes() == (
        FIXTURE_DIRECTORY / "summary.md"
    ).read_bytes()
    assert (output / "results.jsonl").read_bytes() == (
        FIXTURE_DIRECTORY / "regraded-results.jsonl"
    ).read_bytes()
    assert (FIXTURE_DIRECTORY / "regrade-summary.md").read_bytes() == (
        FIXTURE_DIRECTORY / "summary.md"
    ).read_bytes()
    regrade_manifest = benchmark._manifest_from_dict(
        benchmark._read_json(FIXTURE_DIRECTORY / "regrade-manifest.json")
    )
    assert regrade_manifest.source == {
        "run_id": snapshot.manifest.run_id,
        "root_report_kind": "live",
        "manifest_sha256": _sha256_file(FIXTURE_DIRECTORY / "manifest.json"),
        "requests_sha256": _sha256_file(FIXTURE_DIRECTORY / "requests.jsonl"),
        "results_sha256": _sha256_file(FIXTURE_DIRECTORY / "results.jsonl"),
    }
    for result_path in (
        FIXTURE_DIRECTORY / "results.jsonl",
        FIXTURE_DIRECTORY / "regraded-results.jsonl",
    ):
        assert all(
            record["response_id"] is None
            for record in benchmark._read_jsonl(
                result_path, require_canonical=True
            )
        )
    fixture_text = "\n".join(
        path.read_text(encoding="utf-8", errors="strict")
        for path in FIXTURE_DIRECTORY.iterdir()
    ).casefold()
    for forbidden in ("api_key", "bearer ", "client_secret", "tenant_id", "endpoint"):
        assert forbidden not in fixture_text
    assert source_bytes == {
        path.name: path.read_bytes() for path in FIXTURE_DIRECTORY.iterdir()
    }
