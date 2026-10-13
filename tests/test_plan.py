from __future__ import annotations

from pathlib import Path

import pytest

from grader.plan import PlanError, check_ids, export_schema, load_plan, parse_plan
from grader.validate import validate_plan

ROOT = Path(__file__).resolve().parent.parent
BAD = ROOT / "tests" / "fixtures" / "bad_plans"

# fixture file -> a fragment that must appear in one of the error sentences
BAD_PLANS = {
    "unknown_op": "does not match any of the expected tags",
    "missing_tolerance": "exactly one of 'tol_abs' or 'tol_pct'",
    "both_tolerances": "exactly one of 'tol_abs' or 'tol_pct'",
    "extra_field": "(steps[0].windw_ms): unknown field",
    "bad_pin": "step 'pwm': pin D7 is not in the pin map.",
    "field_not_valid": "field 'delay_ms' is not returned by primitive 'freq_duty'",
    "duplicate_id": "id 'pwm' is already used by step 'pwm'",
    "wrong_capability": "measured pin D2 lacks the 'timer_capture' capability",
    "no_expectations": "needs at least one expectation",
    "out_of_range": "window_ms 20000 is out of range",
    "dangling_concurrent": "must be followed by a stimulus step",
    "bad_schema_version": "schema_version",
}


def all_errors(path: Path, pinmap) -> list[str]:
    try:
        plan = load_plan(path)
    except PlanError as exc:
        return exc.errors
    return validate_plan(plan, pinmap)


@pytest.mark.parametrize("plan_path", sorted((ROOT / "plans").glob("*.json")), ids=lambda p: p.stem)
def test_example_plans_are_valid(plan_path: Path, pinmap) -> None:
    plan = load_plan(plan_path)
    assert plan.assignment == plan_path.stem
    assert validate_plan(plan, pinmap) == []


def test_every_bad_fixture_is_covered() -> None:
    assert {p.stem for p in BAD.glob("*.json")} == set(BAD_PLANS)


@pytest.mark.parametrize("name", sorted(BAD_PLANS))
def test_bad_plans_rejected(name: str, pinmap) -> None:
    errors = all_errors(BAD / f"{name}.json", pinmap)
    assert errors, f"{name} should be rejected"
    assert any(BAD_PLANS[name] in e for e in errors), errors


def test_all_errors_reported_at_once(pinmap) -> None:
    raw = {
        "schema_version": "0.1",
        "assignment": "multi",
        "description": "x",
        "steps": [
            {
                "op": "measure", "id": "a", "requirement": "r", "primitive": "freq_duty",
                "pin": "D7", "window_ms": 0,
                "expect": [{"field": "text", "op": "contains", "value": "x"}],
            },
            {"op": "uart_send", "baud": 1234, "data": "hi"},
        ],
    }  # fmt: skip
    errors = validate_plan(parse_plan(raw), pinmap)
    assert len(errors) == 4, errors
    assert any(e.startswith("step #2 (uart_send): baud 1234 is not a standard") for e in errors)
    assert all(e.endswith(".") or e.endswith(").") for e in errors)


def test_schema_errors_name_the_step() -> None:
    raw = {
        "schema_version": "0.1", "assignment": "x", "description": "x",
        "steps": [{"op": "measure", "id": "freq", "requirement": "r", "primitive": "freq_duty",
                   "pin": "D5", "window_ms": 10,
                   "expect": [{"field": "frequency_hz", "op": "approx", "value": 1}]}],
    }  # fmt: skip
    with pytest.raises(PlanError) as exc:
        parse_plan(raw)
    assert exc.value.errors[0].startswith("step 'freq' (steps[0].expect[0]):")


def test_check_ids_disambiguate_repeated_fields() -> None:
    plan = load_plan(ROOT / "plans" / "pwm_1khz.json")
    step = plan.steps[0]
    step.expect.append(step.expect[0])
    assert check_ids(step) == ["pwm.frequency_hz", "pwm.duty_pct", "pwm.frequency_hz#2"]


def test_committed_schema_is_fresh() -> None:
    committed = (ROOT / "schemas" / "plan.schema.json").read_text(encoding="utf-8")
    assert committed == export_schema(), "run: grader export-schema"
