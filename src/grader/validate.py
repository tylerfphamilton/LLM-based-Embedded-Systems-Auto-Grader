"""Semantic plan validation: everything the JSON Schema cannot express.

Every problem is reported (not just the first) as one self-contained sentence, because
these messages are fed back to the LLM so it can repair its plan.
"""

from __future__ import annotations

from typing import Any

from grader.pinmap import RIG_ONLY_CAPS, PinMap
from grader.plan import (
    PLACEHOLDER,
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

# What the firmware's ARM accepts, and how many it can run at once (docs/protocol.md).
ARMABLE = ("edge_delay", "freq_duty", "logic_trace", "uart_read")
MAX_ARMED = 4
DRIVE_TYPES = (DriveLevelStep, DrivePulseStep, DriveBounceStep)

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
    elif pinmap.caps(pin) & RIG_ONLY_CAPS:
        rig_caps = ", ".join(sorted(pinmap.caps(pin) & RIG_ONLY_CAPS))
        errors.append(
            f"{where}: pin {pin} is reserved for the rig ({rig_caps}) and cannot be used "
            "by a plan step."
        )
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
    if isinstance(step, DRIVE_TYPES):
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
        line = _edge_line(step.from_pin, pinmap)
        if (
            step.from_pin != step.to_pin
            and line is not None
            and line == _edge_line(step.to_pin, pinmap)
        ):
            errors.append(_shared_line(where, step.from_pin, step.to_pin, line))
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


def _edge_line(pin: str, pinmap: PinMap) -> int | None:
    """The STM32 edge-interrupt line of a wired pin: its pin number (PB3 -> 3)."""
    stm32 = pinmap.pins[pin].stm32 if pinmap.has(pin) else ""
    if len(stm32) >= 3 and stm32[0] == "P" and stm32[1].isalpha() and stm32[2:].isdigit():
        return int(stm32[2:])
    return None


def _shared_line(where: str, a: str, b: str, line: int) -> str:
    return (
        f"{where}: pins {a} and {b} share STM32 edge-interrupt line {line}, so the measuring "
        "board cannot watch both at once."
    )


def _pins_used(step: MeasureBase, pinmap: PinMap) -> list[str]:
    if isinstance(step, EdgeDelayStep):
        return list(dict.fromkeys([step.from_pin, step.to_pin]))
    if isinstance(step, UartReadStep):
        return pinmap.pins_with("uart_rx")
    pin = getattr(step, "pin", None)
    return [pin] if pin else []


def _check_group(
    errors: _Errors, group: list[int], stim_i: int, plan: Plan, pinmap: PinMap
) -> None:
    """Measurements armed together before one stimulus, as the firmware's ARM allows."""
    steps, stimulus = plan.steps, plan.steps[stim_i]
    if len(group) > MAX_ARMED:
        errors.append(
            f"{_label(steps[group[0]], group[0])}: {len(group)} concurrent measure steps run "
            f"before {_label(stimulus, stim_i)}, but the measuring board runs at most "
            f"{MAX_ARMED} at once."
        )
    kinds: dict[str, str] = {}
    pins: dict[str, str] = {}  # pin -> step that measures it
    lines: dict[int, tuple[str, str]] = {}  # edge-interrupt line -> (pin, step)
    for i in group:
        step, where = steps[i], _label(steps[i], i)
        if step.primitive not in ARMABLE:
            errors.append(
                f"{where}: primitive '{step.primitive}' cannot run concurrently with a "
                f"stimulus; only {', '.join(ARMABLE)} can."
            )
        if step.primitive in kinds:
            errors.append(
                f"{where}: {kinds[step.primitive]} already runs a '{step.primitive}' "
                "measurement before the same stimulus, and the measuring board runs one of "
                "each kind at a time."
            )
        kinds.setdefault(step.primitive, where)
        used = _pins_used(step, pinmap)
        for pin in used:
            if pin in pins:
                errors.append(
                    f"{where}: pin {pin} is already measured by {pins[pin]} before the same "
                    "stimulus; concurrent measurements cannot share a pin."
                )
            elif isinstance(step, EdgeDelayStep | LogicTraceStep):
                line = _edge_line(pin, pinmap)
                other = lines.get(line) if line is not None else None
                if other and other[1] != where:
                    errors.append(_shared_line(where, pin, other[0], line))
        for pin in used:
            pins.setdefault(pin, where)
            if (
                isinstance(step, EdgeDelayStep | LogicTraceStep)
                and (line := _edge_line(pin, pinmap)) is not None
            ):
                lines.setdefault(line, (pin, where))
        uart_send = isinstance(stimulus, UartSendStep)
        if uart_send and isinstance(step, UartReadStep) and step.baud != stimulus.baud:
            errors.append(
                f"{where}: reads at {step.baud} baud while {_label(stimulus, stim_i)} sends "
                f"at {stimulus.baud} baud, but the measuring board's UART has one baud."
            )


def _check_concurrency(errors: _Errors, plan: Plan, pinmap: PinMap) -> None:
    steps = plan.steps
    stimulus_of: dict[int, Any] = {}  # concurrent measure step index -> its stimulus step
    i = 0
    while i < len(steps):
        if not (is_measure(steps[i]) and steps[i].concurrent_with_next):
            i += 1
            continue
        j = i
        while j < len(steps) and is_measure(steps[j]) and steps[j].concurrent_with_next:
            j += 1
        group = list(range(i, j))
        if j >= len(steps) or not isinstance(steps[j], STIMULUS_TYPES):
            what = "the end of the plan" if j >= len(steps) else _label(steps[j], j)
            for k in group:
                errors.append(
                    f"{_label(steps[k], k)}: concurrent_with_next is set, but it is followed by "
                    f"{what}; it must be followed by a stimulus step (drive, uart_send or "
                    "dac_set), optionally after other concurrent measure steps."
                )
        else:
            stimulus_of.update({k: steps[j] for k in group})
            _check_group(errors, group, j, plan, pinmap)
        i = j

    # A delay from a pin the rig drives can only start when the rig drives that pin.
    for i, step in enumerate(steps):
        if isinstance(step, EdgeDelayStep) and "drive" in pinmap.caps(step.from_pin):
            stim = stimulus_of.get(i)
            if not (isinstance(stim, DRIVE_TYPES) and stim.pin == step.from_pin):
                errors.append(
                    f"{_label(step, i)}: from_pin {step.from_pin} is driven by the measuring "
                    "board, so this delay only starts when the board drives it; set "
                    "concurrent_with_next: true and put a drive step on "
                    f"{step.from_pin} right after this measure step (and any other "
                    "concurrent ones)."
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

    _check_concurrency(errors, plan, pinmap)
    _check_params(errors, plan)
    return list(errors)


# ------------------------------------------------------------------ per-student params

TEXT_VALUE_OPS = {"eq", "ne", "contains", "matches"}
PLACEHOLDER_HOME = (
    "placeholders are only allowed in text expectation values (eq, ne, contains or matches "
    "on 'text'), in uart_send data, and in the description, requirement, assumptions and "
    "not_graded texts"
)


def _strings(node: Any, path: tuple = ()) -> Any:
    """Every string in a dumped plan, with its path, e.g. ("steps", 3, "expect", 0, "value")."""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, list):
        for i, x in enumerate(node):
            yield from _strings(x, (*path, i))
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from _strings(v, (*path, k))


def _placeholder_allowed(path: tuple, raw: dict) -> bool:
    match path:
        case ("description",) | ("assumptions", int()) | ("not_graded", int(), _):
            return True
        case ("steps", int(), "requirement"):
            return True
        case ("steps", int() as i, "data"):
            return raw["steps"][i]["op"] == "uart_send"
        case ("steps", int() as i, "expect", int() as j, "value"):
            exp = raw["steps"][i]["expect"][j]
            return exp["field"] in TEXT_FIELDS and exp["op"] in TEXT_VALUE_OPS
    return False


def _check_params(errors: _Errors, plan: Plan) -> None:
    """``{{name}}`` placeholders: declared, used, and only inside string fields (D63)."""
    for name in sorted({p for p in plan.params if plan.params.count(p) > 1}):
        errors.append(f"params: '{name}' is listed more than once.")
    raw = plan.model_dump(mode="json")
    used: set[str] = set()
    for path, text in _strings(raw):
        names = PLACEHOLDER.findall(text)
        if not names or path[:1] == ("params",):
            continue
        in_step = path[0] == "steps"
        where = _label(plan.steps[path[1]], path[1]) if in_step else "plan"
        rel = path[2:] if in_step else path
        field = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in rel).lstrip(".")
        shown = ", ".join("{{" + n + "}}" for n in names)
        if not _placeholder_allowed(path, raw):
            errors.append(f"{where}: field '{field}' contains {shown}, but {PLACEHOLDER_HOME}.")
        for n in names:
            if n in plan.params:
                used.add(n)
            else:
                errors.append(
                    f"{where}: placeholder {{{{{n}}}}} in '{field}' is not declared in 'params'."
                )
    for name in dict.fromkeys(plan.params):
        if name not in used:
            errors.append(f"params: '{name}' is declared but never used as {{{{{name}}}}}.")
