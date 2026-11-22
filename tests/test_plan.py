from __future__ import annotations

from pathlib import Path

import pytest

from grader.plan import PlanError, check_ids, export_schema, instantiate, load_plan, parse_plan
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
    # A templated plan must stay valid once filled in (its matches regexes must compile).
    for dummy in ("0", "a.b+c"):
        filled = instantiate(plan, {p: dummy for p in plan.params})
        assert validate_plan(filled, pinmap) == []


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


# --- concurrent measurements: what the firmware's ARM accepts (docs/protocol.md) ---------

LED_DELAY = {
    "op": "measure", "id": "led", "requirement": "r", "primitive": "edge_delay",
    "from_pin": "D2", "from_edge": "falling", "to_pin": "D13", "to_edge": "any",
    "timeout_ms": 100, "expect": [{"field": "delay_ms", "op": "le", "value": 20}],
}  # fmt: skip
TRACE_D13 = {
    "op": "measure", "id": "trace", "requirement": "r", "primitive": "logic_trace",
    "pin": "D13", "window_ms": 200, "expect": [{"field": "edge_count", "op": "eq", "value": 1}],
}  # fmt: skip
UART_ON = {
    "op": "measure", "id": "msg", "requirement": "r", "primitive": "uart_read",
    "baud": 9600, "window_ms": 200, "expect": [{"field": "text", "op": "contains", "value": "ON"}],
}  # fmt: skip
PRESS = {"op": "drive", "pin": "D2", "action": "bounce", "count": 5, "interval_us": 200,
         "final_level": "low"}  # fmt: skip


def _errors(steps: list[dict], pinmap) -> list[str]:
    raw = {"schema_version": "0.1", "assignment": "t", "description": "x", "steps": steps}
    return validate_plan(parse_plan(raw), pinmap)


def _armed(step: dict, sid: str | None = None) -> dict:
    return {**step, "concurrent_with_next": True, **({"id": sid} if sid else {})}


def test_button_style_group_is_valid(pinmap) -> None:
    assert _errors([_armed(LED_DELAY), _armed(UART_ON), PRESS], pinmap) == []


def test_concurrent_measurements_cannot_share_a_pin(pinmap) -> None:
    (err,) = _errors([_armed(LED_DELAY), _armed(TRACE_D13), PRESS], pinmap)
    assert "step 'trace': pin D13 is already measured by step 'led'" in err


def test_one_measurement_of_each_kind_per_group(pinmap) -> None:
    errors = _errors([_armed(UART_ON), _armed(UART_ON, "msg2"), PRESS], pinmap)
    assert any("step 'msg2': step 'msg' already runs a 'uart_read'" in e for e in errors), errors


def test_uart_send_baud_must_match_an_armed_read(pinmap) -> None:
    send = {"op": "uart_send", "baud": 115200, "data": "hi"}
    (err,) = _errors([_armed(UART_ON), send], pinmap)
    assert "reads at 9600 baud while step #2 (uart_send) sends at 115200 baud" in err


def test_at_most_four_concurrent_measurements(pinmap) -> None:
    freq = {
        "op": "measure", "id": "f", "requirement": "r", "primitive": "freq_duty", "pin": "D5",
        "window_ms": 100, "expect": [{"field": "edge_count", "op": "ge", "value": 1}],
    }  # fmt: skip
    trace = {**TRACE_D13, "pin": "D5"}
    group = [_armed(LED_DELAY), _armed(UART_ON), _armed(freq), _armed(trace), _armed(UART_ON, "m2")]
    errors = _errors([*group, PRESS], pinmap)
    assert any("5 concurrent measure steps" in e and "at most 4" in e for e in errors), errors


def test_only_armable_primitives_run_concurrently(pinmap) -> None:
    adc = {
        "op": "measure", "id": "adc", "requirement": "r", "primitive": "analog_read", "pin": "A0",
        "samples": 10, "expect": [{"field": "mean_mv", "op": "le", "value": 100}],
    }  # fmt: skip
    errors = _errors([_armed(adc), PRESS], pinmap)
    assert any("primitive 'analog_read' cannot run concurrently" in e for e in errors), errors


def test_delay_from_a_driven_pin_needs_that_drive_next(pinmap) -> None:
    fix = "from_pin D2 is driven by the measuring board"
    assert any(fix in e for e in _errors([LED_DELAY, PRESS], pinmap))  # not concurrent
    send = {"op": "uart_send", "baud": 9600, "data": "hi"}
    assert any(fix in e for e in _errors([_armed(LED_DELAY), send], pinmap))  # wrong stimulus
    # A delay that starts on a student output (D13 high time) needs no drive.
    high_time = {**LED_DELAY, "from_pin": "D13", "from_edge": "rising", "to_edge": "falling"}
    assert _errors([high_time], pinmap) == []


def test_pins_sharing_an_edge_interrupt_line(pinmap) -> None:
    shared = pinmap.model_copy(deep=True)
    shared.pins["D5"].stm32 = "PA3"  # same line as D13 (PB3)
    errors = _errors([_armed(LED_DELAY), _armed({**TRACE_D13, "pin": "D5"}), PRESS], shared)
    assert any("pins D5 and D13 share STM32 edge-interrupt line 3" in e for e in errors), errors
    delay = {**LED_DELAY, "from_pin": "D5", "from_edge": "rising"}
    assert any("pins D5 and D13 share" in e for e in _errors([delay], shared))
    assert _errors([_armed(LED_DELAY), _armed({**TRACE_D13, "pin": "D5"}), PRESS], pinmap) == []
