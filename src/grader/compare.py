"""Expectation + measurement -> verdict. Pure, deterministic, no I/O.

Rules:
* A rig fault (``Measurement.error``) or a reply missing the field  -> ERROR.
* A null value (e.g. no signal) is a valid measurement               -> FAIL (unless is_null).
* For approx/le/ge/lt/gt/in_range, a value within the rig's known measurement error of a
  tolerance boundary                                                  -> BORDERLINE.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from grader.plan import (
    ApproxExpectation,
    CompareExpectation,
    Expectation,
    NullExpectation,
    RangeExpectation,
    TextExpectation,
    unit_for,
)
from grader.rig_profile import RigProfile


class Verdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    BORDERLINE = "BORDERLINE"
    ERROR = "ERROR"
    NOT_GRADED = "NOT_GRADED"


@dataclass(frozen=True)
class Measurement:
    """The result of one measurement step: either reply fields or a rig error."""

    fields: Mapping[str, Any] | None = None
    error: str | None = None

    @classmethod
    def ok(cls, fields: Mapping[str, Any]) -> Measurement:
        return cls(fields=dict(fields))

    @classmethod
    def rig_error(cls, message: str) -> Measurement:
        return cls(error=message)


@dataclass(frozen=True)
class Outcome:
    verdict: Verdict
    measured: Any
    reason: str


# ------------------------------------------------------------------------- formatting


def fmt_num(x: float) -> str:
    if isinstance(x, float) and x.is_integer() and abs(x) < 1e15:
        return str(int(x))
    return f"{x:.5g}"


def _with_unit(x: float, field: str) -> str:
    unit = unit_for(field)
    if not unit:
        return fmt_num(x)
    return f"{fmt_num(x)}{'' if unit == '%' else ' '}{unit}"


def fmt_measured(value: Any, field: str) -> str:
    if value is None:
        return "no value (null)"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        shown = ", ".join(fmt_measured(v, "") for v in value[:8])
        return f"[{shown}{', …' if len(value) > 8 else ''}]"
    if isinstance(value, int | float):
        return _with_unit(value, field)
    return str(value)


def describe(exp: Expectation) -> str:
    """Human description of what is expected, e.g. '≈ 1000 Hz ± 2%'."""
    f = exp.field
    match exp:
        case ApproxExpectation(tol_pct=pct) if pct is not None:
            return f"≈ {_with_unit(exp.value, f)} ± {fmt_num(pct)}%"
        case ApproxExpectation(tol_abs=tol):
            assert tol is not None
            tol_text = f"{fmt_num(tol)} pt" if unit_for(f) == "%" else _with_unit(tol, f)
            return f"≈ {_with_unit(exp.value, f)} ± {tol_text}"
        case CompareExpectation():
            sym = {"eq": "=", "ne": "≠", "le": "≤", "ge": "≥", "lt": "<", "gt": ">"}[exp.op]
            shown = (
                json.dumps(exp.value, ensure_ascii=False)
                if isinstance(exp.value, str)
                else _with_unit(exp.value, f)
            )
            return f"{sym} {shown}"
        case RangeExpectation():
            return f"{_with_unit(exp.low, f)} – {_with_unit(exp.high, f)}"
        case TextExpectation(op="contains"):
            return f"contains {json.dumps(exp.value, ensure_ascii=False)}"
        case TextExpectation():
            return f"matches /{exp.value}/"
        case NullExpectation(op="is_null"):
            return "no value (null)"
        case NullExpectation():
            return "any value (not null)"
    raise TypeError(type(exp))


def tolerance(exp: Expectation) -> dict[str, float] | None:
    if isinstance(exp, ApproxExpectation):
        return {"tol_abs": exp.tol_abs} if exp.tol_abs is not None else {"tol_pct": exp.tol_pct}  # type: ignore[dict-item]
    return None


# --------------------------------------------------------------------------- compare


def _is_number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def _bounded(
    v: float, lo: float | None, hi: float | None, ok: bool, err: float, exp: Expectation
) -> Outcome:
    """Shared verdict for numeric checks with one or two boundaries."""
    shown = _with_unit(v, exp.field)
    for bound in (lo, hi):
        if bound is not None and err > 0 and abs(v - bound) <= err:
            return Outcome(
                Verdict.BORDERLINE,
                v,
                f"measured {shown} is within the rig's measurement error "
                f"(±{_with_unit(err, exp.field)}) of the limit {_with_unit(bound, exp.field)}; "
                f"expected {describe(exp)}. Cannot decide reliably.",
            )
    if ok:
        return Outcome(Verdict.PASS, v, f"measured {shown}; expected {describe(exp)}")
    return Outcome(Verdict.FAIL, v, f"measured {shown}, but expected {describe(exp)}")


def compare(exp: Expectation, m: Measurement, profile: RigProfile) -> Outcome:
    """Decide one expectation. Never raises for odd measurement values."""
    if m.error is not None:
        return Outcome(Verdict.ERROR, None, f"rig error: {m.error}")
    fields = m.fields or {}
    if exp.field not in fields:
        return Outcome(
            Verdict.ERROR, None, f"rig error: the reply did not include field '{exp.field}'"
        )
    v = fields[exp.field]

    if isinstance(exp, NullExpectation):
        want_null = exp.op == "is_null"
        if (v is None) == want_null:
            return Outcome(Verdict.PASS, v, f"measured {fmt_measured(v, exp.field)}")
        return Outcome(
            Verdict.FAIL,
            v,
            f"measured {fmt_measured(v, exp.field)}, but expected {describe(exp)}",
        )

    if v is None:
        return Outcome(
            Verdict.FAIL,
            None,
            f"nothing was measured for '{exp.field}' (null, e.g. no signal or no response); "
            f"expected {describe(exp)}",
        )

    if isinstance(exp, TextExpectation):
        if exp.op == "contains" and isinstance(v, str | list):
            ok = exp.value in v
        elif exp.op == "matches" and isinstance(v, str):
            ok = re.search(exp.value, v) is not None
        else:
            return Outcome(
                Verdict.ERROR, v, f"rig error: '{exp.field}' has unexpected type for '{exp.op}'"
            )
        verdict = Verdict.PASS if ok else Verdict.FAIL
        joiner = "; expected" if ok else ", but expected"
        return Outcome(verdict, v, f"received {fmt_measured(v, exp.field)}{joiner} {describe(exp)}")

    if isinstance(exp, CompareExpectation) and exp.op in ("eq", "ne"):
        if isinstance(exp.value, str) != isinstance(v, str):
            return Outcome(
                Verdict.ERROR, v, f"rig error: '{exp.field}' has unexpected type for '{exp.op}'"
            )
        ok = (v == exp.value) if exp.op == "eq" else (v != exp.value)
        verdict = Verdict.PASS if ok else Verdict.FAIL
        joiner = "; expected" if ok else ", but expected"
        return Outcome(verdict, v, f"measured {fmt_measured(v, exp.field)}{joiner} {describe(exp)}")

    if not _is_number(v):
        return Outcome(Verdict.ERROR, v, f"rig error: '{exp.field}' should be numeric, got {v!r}")
    err = profile.error(exp.field, v)

    if isinstance(exp, ApproxExpectation):
        lo, hi = exp.bounds()
        return _bounded(v, lo, hi, lo <= v <= hi, err, exp)
    if isinstance(exp, RangeExpectation):
        return _bounded(v, exp.low, exp.high, exp.low <= v <= exp.high, err, exp)
    assert isinstance(exp, CompareExpectation) and _is_number(exp.value)
    b = float(exp.value)  # type: ignore[arg-type]
    ok = {"le": v <= b, "lt": v < b, "ge": v >= b, "gt": v > b}[exp.op]
    return _bounded(v, b, None, ok, err, exp)
