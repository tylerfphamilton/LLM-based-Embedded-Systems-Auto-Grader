from __future__ import annotations

from typing import Any

import pytest
from pydantic import TypeAdapter

from grader.compare import Measurement, Verdict, compare, describe
from grader.plan import Expectation
from grader.rig_profile import RigProfile

P, F, B, E = Verdict.PASS, Verdict.FAIL, Verdict.BORDERLINE, Verdict.ERROR

PROFILE = RigProfile.model_validate(
    {"fields": {"frequency_hz": {"pct": 0.05}, "delay_ms": {"abs": 0.02}, "mean_mv": {"abs": 5}}}
)
NO_ERROR = RigProfile()

_exp = TypeAdapter(Expectation)


def exp(**kw: Any):
    return _exp.validate_python(kw)


def verdict(e, value: Any, profile: RigProfile = PROFILE) -> Verdict:
    return compare(e, Measurement.ok({e.field: value}), profile).verdict


FREQ = exp(field="frequency_hz", op="approx", value=1000, tol_pct=2)  # 980..1020, err ~0.5
DUTY = exp(field="duty_pct", op="approx", value=25, tol_abs=1)  # no rig error configured


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1000.0, P),
        (981.0, P),
        (1019.0, P),
        (979.0, F),
        (1021.0, F),
        (500.0, F),
        (1019.8, B),  # inside, but within 0.51 of 1020
        (1020.3, B),  # outside, but within 0.51 of 1020
        (979.6, B),
        (980.6, P),  # 0.6 > 0.49 from 980
        (1000, P),  # integers are numbers too
    ],
)
def test_approx_pct_with_borderline(value: float, expected: Verdict) -> None:
    assert verdict(FREQ, value) == expected


@pytest.mark.parametrize(("value", "expected"), [(25.0, P), (26.0, P), (26.01, F), (23.99, F)])
def test_approx_abs_without_rig_error_has_no_borderline(value: float, expected: Verdict) -> None:
    assert verdict(DUTY, value) == expected


@pytest.mark.parametrize(
    ("op", "value", "measured", "expected"),
    [
        ("le", 20, 19.0, P),
        ("le", 20, 20.0, B),
        ("le", 20, 20.03, F),
        ("le", 20, 20.01, B),
        ("lt", 20, 19.9, P),
        ("lt", 20, 20.0, B),
        ("lt", 20, 25.0, F),
        ("ge", 5, 6.0, P),
        ("ge", 5, 4.0, F),
        ("ge", 5, 4.99, B),
        ("gt", 5, 5.5, P),
        ("gt", 5, 4.5, F),
        ("eq", 1, 1, P),
        ("eq", 1, 5, F),
        ("ne", 0, 3, P),
        ("ne", 0, 0, F),
    ],
)
def test_numeric_comparisons(op: str, value: float, measured: float, expected: Verdict) -> None:
    assert verdict(exp(field="delay_ms", op=op, value=value), measured) == expected


def test_eq_on_counts_has_no_borderline_zone() -> None:
    e = exp(field="to_edge_count", op="eq", value=1)
    assert verdict(e, 1) == P and verdict(e, 2) == F


@pytest.mark.parametrize(
    ("measured", "expected"), [(1650.0, P), (1500.0, B), (1797.0, B), (1400.0, F), (1900.0, F)]
)
def test_in_range(measured: float, expected: Verdict) -> None:
    assert verdict(exp(field="mean_mv", op="in_range", low=1500, high=1800), measured) == expected


@pytest.mark.parametrize(
    ("e", "measured", "expected"),
    [
        (exp(field="text", op="contains", value="ON"), "LED ON\r\n", P),
        (exp(field="text", op="contains", value="ON"), "OFF\r\n", F),
        (exp(field="text", op="matches", value=r"^\s*ON\s*$"), "ON\r\n", P),
        (exp(field="text", op="matches", value=r"^\s*ON\s*$"), "ON\r\nOFF\r\n", F),
        (exp(field="text", op="eq", value="ON"), "ON", P),
        (exp(field="text", op="ne", value="ON"), "ON", F),
        (exp(field="transactions", op="contains", value="R:0x68:0x75"), ["R:0x68:0x75"], P),
        (exp(field="transactions", op="contains", value="W:0x68:0x6B"), [], F),
    ],
)
def test_text_and_list_ops(e, measured: Any, expected: Verdict) -> None:
    assert verdict(e, measured) == expected


def test_null_ops() -> None:
    assert verdict(exp(field="delay_ms", op="is_null"), None) == P
    assert verdict(exp(field="delay_ms", op="is_null"), 3.0) == F
    assert verdict(exp(field="delay_ms", op="not_null"), 3.0) == P
    assert verdict(exp(field="delay_ms", op="not_null"), None) == F


@pytest.mark.parametrize(
    "e",
    [
        FREQ,
        DUTY,
        exp(field="delay_ms", op="le", value=20),
        exp(field="to_edge_count", op="eq", value=1),
        exp(field="mean_mv", op="in_range", low=1, high=2),
        exp(field="text", op="contains", value="ON"),
        exp(field="text", op="matches", value="ON"),
    ],
)
def test_null_is_fail_with_clear_reason_never_exception(e) -> None:
    out = compare(e, Measurement.ok({e.field: None}), PROFILE)
    assert out.verdict == F
    assert "nothing was measured" in out.reason and "no signal" in out.reason


def test_rig_error_is_error_not_fail() -> None:
    out = compare(FREQ, Measurement.rig_error("ERR TIMEOUT capture"), PROFILE)
    assert out.verdict == E and "TIMEOUT" in out.reason


def test_missing_field_is_error() -> None:
    out = compare(FREQ, Measurement.ok({"duty_pct": 25.0}), PROFILE)
    assert out.verdict == E and "did not include field 'frequency_hz'" in out.reason


@pytest.mark.parametrize(
    ("e", "measured"),
    [
        (FREQ, "fast"),
        (exp(field="text", op="contains", value="x"), 3),
        (exp(field="text", op="eq", value="ON"), 1),
    ],
)
def test_wrong_type_from_rig_is_error(e, measured: Any) -> None:
    assert verdict(e, measured) == E


def test_reasons_are_readable() -> None:
    assert compare(FREQ, Measurement.ok({"frequency_hz": 500.0}), PROFILE).reason == (
        "measured 500 Hz, but expected ≈ 1000 Hz ± 2%"
    )
    borderline = compare(FREQ, Measurement.ok({"frequency_hz": 1019.8}), PROFILE).reason
    assert "within the rig's measurement error" in borderline and "1020 Hz" in borderline


def test_describe() -> None:
    assert describe(DUTY) == "≈ 25% ± 1 pt"
    assert describe(exp(field="delay_ms", op="le", value=20)) == "≤ 20 ms"
    assert describe(exp(field="mean_mv", op="in_range", low=1500, high=1800)) == "1500 mV – 1800 mV"
    assert describe(exp(field="text", op="contains", value="ON")) == 'contains "ON"'


def test_deterministic() -> None:
    m = Measurement.ok({"frequency_hz": 1019.8})
    assert len({compare(FREQ, m, PROFILE) for _ in range(5)}) == 1
