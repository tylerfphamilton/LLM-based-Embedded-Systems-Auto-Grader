"""Semantic plan validation: everything the JSON Schema cannot express.

Every problem is reported (not just the first) as one self-contained sentence, because
these messages are fed back to the LLM so it can repair its plan.
"""

from __future__ import annotations

from typing import Any

from grader.pinmap import PinMap
from grader.plan import (
    PRIMITIVE_FIELDS,
    STIMULUS_TYPES,
    AnalogReadStep,
    CompareExpectation,
    DacSetStep,
    DriveBounceStep,
    DriveLevelStep,
    DrivePulseStep,
    EdgeDelayStep,
    FreqDutyStep,
    I2cEmuStep,
    I2cLogStep,
    LogicTraceStep,
    MeasureBase,
    Plan,
    UartReadStep,
    UartSendStep,
    WaitStep,
    check_ids,
    is_measure,
)

STANDARD_BAUDS = (300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400)

TEXT_FIELDS = {"text"}
LIST_FIELDS = {"edges_ms", "transactions"}

NUMERIC_OPS = {"approx", "eq", "ne", "le", "ge", "lt", "gt", "in_range", "is_null", "not_null"}
TEXT_OPS = {"eq", "ne", "contains", "matches", "is_null", "not_null"}
LIST_OPS = {"contains", "is_null", "not_null"}


def _label(step: Any, index: int) -> str:
    if getattr(step, "id", None):
        return f"step '{step.id}'"
    return f"step #{index + 1} ({step.op})"


class _Errors(list[str]):
    def range(self, where: str, name: str, value: int, lo: int, hi: int, unit: str = "") -> None:
        if not lo <= value <= hi:
            self.append(f"{where}: {name} {value}{unit} is out of range ({lo}–{hi}{unit}).")


def _check_pin(errors: _Errors, where: str, role: str, pin: str, cap: str, pinmap: PinMap) -> None:
    if not pinmap.has(pin):
        errors.append(f"{where}: pin {pin} is not in the pin map.")
    elif cap not in pinmap.caps(pin):
        have = ", ".join(sorted(pinmap.caps(pin))) or "none"
        errors.append(f"{where}: {role} pin {pin} lacks the '{cap}' capability (it has: {have}).")


def _require_bus(errors: _Errors, where: str, caps: tuple[str, ...], pinmap: PinMap) -> None:
    for cap in caps:
        if not pinmap.pins_with(cap):
            errors.append(f"{where}: the pin map has no pin with the '{cap}' capability.")


def _check_expectations(errors: _Errors, where: str, step: MeasureBase) -> None:
    if not step.expect:
        errors.append(f"{where}: a measure step needs at least one expectation in 'expect'.")
    valid = PRIMITIVE_FIELDS[step.primitive]  # type: ignore[attr-defined]
    for i, exp in enumerate(step.expect):
        ew = f"{where} expectation #{i + 1}"
        if exp.field not in valid:
            errors.append(
                f"{ew}: field '{exp.field}' is not returned by primitive "
                f"'{step.primitive}' (valid: {', '.join(valid)})."  # type: ignore[attr-defined]
            )
            continue
        if exp.field in TEXT_FIELDS:
            kind, allowed = "text", TEXT_OPS
        elif exp.field in LIST_FIELDS:
            kind, allowed = "list", LIST_OPS
        else:
            kind, allowed = "numeric", NUMERIC_OPS
        if exp.op not in allowed:
            errors.append(
                f"{ew}: op '{exp.op}' cannot be used on {kind} field '{exp.field}' "
                f"(allowed: {', '.join(sorted(allowed))})."
            )
        elif isinstance(exp, CompareExpectation):
            if kind == "numeric" and isinstance(exp.value, str):
                errors.append(f"{ew}: field '{exp.field}' is numeric but value is a string.")
            if kind == "text" and not isinstance(exp.value, str):
                errors.append(f"{ew}: field '{exp.field}' is text but value is a number.")


def _check_step(errors: _Errors, where: str, step: Any, pinmap: PinMap) -> None:
    if isinstance(step, DriveLevelStep | DrivePulseStep | DriveBounceStep):
        _check_pin(errors, where, "driven", step.pin, "drive", pinmap)
        if isinstance(step, DrivePulseStep):
            errors.range(where, "width_ms", step.width_ms, 1, 10000)
        if isinstance(step, DriveBounceStep):
            errors.range(where, "count", step.count, 1, 100)
            errors.range(where, "interval_us", step.interval_us, 10, 100000)
    elif isinstance(step, WaitStep):
        errors.range(where, "ms", step.ms, 0, 60000)
    elif isinstance(step, UartSendStep):
        _check_baud(errors, where, step.baud)
        _require_bus(errors, where, ("uart_tx",), pinmap)
        if not 1 <= len(step.payload()) <= 256:
            errors.append(f"{where}: uart_send payload must be 1–256 bytes.")
    elif isinstance(step, DacSetStep):
        _check_pin(errors, where, "DAC", step.pin, "dac", pinmap)
        errors.range(where, "mv", step.mv, 0, 3300)
    elif isinstance(step, I2cEmuStep):
        _require_bus(errors, where, ("i2c_sda", "i2c_scl"), pinmap)
        errors.range(where, "addr", step.addr, 0x08, 0x77)
        for reg, val in step.register_items():
            errors.range(where, "register", reg, 0, 255)
            errors.range(where, f"value of register {reg:#04x}", val, 0, 255)
    elif isinstance(step, FreqDutyStep):
        _check_pin(errors, where, "measured", step.pin, "timer_capture", pinmap)
        errors.range(where, "window_ms", step.window_ms, 1, 10000)
    elif isinstance(step, EdgeDelayStep):
        _check_pin(errors, where, "from", step.from_pin, "gpio", pinmap)
        _check_pin(errors, where, "to", step.to_pin, "timer_capture", pinmap)
        errors.range(where, "timeout_ms", step.timeout_ms, 1, 10000)
    elif isinstance(step, LogicTraceStep):
        _check_pin(errors, where, "traced", step.pin, "gpio", pinmap)
        errors.range(where, "window_ms", step.window_ms, 1, 10000)
    elif isinstance(step, UartReadStep):
        _check_baud(errors, where, step.baud)
        _require_bus(errors, where, ("uart_rx",), pinmap)
        errors.range(where, "window_ms", step.window_ms, 1, 10000)
    elif isinstance(step, I2cLogStep):
        _require_bus(errors, where, ("i2c_sda", "i2c_scl"), pinmap)
        errors.range(where, "window_ms", step.window_ms, 1, 10000)
    elif isinstance(step, AnalogReadStep):
        _check_pin(errors, where, "analog", step.pin, "analog_in", pinmap)
        errors.range(where, "samples", step.samples, 1, 10000)


def _check_baud(errors: _Errors, where: str, baud: int) -> None:
    if baud not in STANDARD_BAUDS:
        errors.append(
            f"{where}: baud {baud} is not a standard rate ({', '.join(map(str, STANDARD_BAUDS))})."
        )


def _check_concurrency(errors: _Errors, plan: Plan) -> None:
    steps = plan.steps
    for i, step in enumerate(steps):
        if not (is_measure(step) and step.concurrent_with_next):
            continue
        j = i + 1
        while j < len(steps) and is_measure(steps[j]) and steps[j].concurrent_with_next:
            j += 1
        if j >= len(steps) or not isinstance(steps[j], STIMULUS_TYPES):
            what = "the end of the plan" if j >= len(steps) else _label(steps[j], j)
            errors.append(
                f"{_label(step, i)}: concurrent_with_next is set, but it is followed by {what}; "
                "it must be followed by a stimulus step (drive, uart_send or dac_set), "
                "optionally after other concurrent measure steps."
            )


def validate_plan(plan: Plan, pinmap: PinMap) -> list[str]:
    """Return every semantic error in ``plan`` (empty list means valid)."""
    errors = _Errors()
    errors.range("setup", "boot_wait_ms", plan.setup.boot_wait_ms, 0, 10000)

    seen: dict[str, str] = {}
    for i, step in enumerate(plan.steps):
        where = _label(step, i)
        ids = [step.id] if getattr(step, "id", None) else []
        if is_measure(step):
            ids += check_ids(step)
        for sid in ids:
            if sid in seen:
                errors.append(f"{where}: id '{sid}' is already used by {seen[sid]}.")
            else:
                seen[sid] = where
        _check_step(errors, where, step, pinmap)
        if is_measure(step):
            _check_expectations(errors, where, step)

    _check_concurrency(errors, plan)
    return list(errors)
