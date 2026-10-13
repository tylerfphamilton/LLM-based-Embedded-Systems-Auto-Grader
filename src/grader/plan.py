"""Test-plan schema (pydantic v2) and JSON Schema export.

A plan is *data*: the LLM writes it once per assignment, and the runner interprets it.
Structure-level rules live here; rules that need the pin map or cross-step context live
in ``validate.py``.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

SCHEMA_VERSION = "0.1"
ID_PATTERN = r"^[A-Za-z][A-Za-z0-9_\-]*$"

Edge = Literal["rising", "falling", "any"]
Level = Literal["high", "low"]


class StrictModel(BaseModel):
    """Base for every plan model: unknown keys are errors, no type coercion."""

    model_config = ConfigDict(extra="forbid", strict=True)


# --------------------------------------------------------------------------- expectations


class ApproxExpectation(StrictModel):
    op: Literal["approx"]
    field: str
    value: float
    tol_abs: float | None = None
    tol_pct: float | None = None

    @model_validator(mode="after")
    def _one_tolerance(self) -> ApproxExpectation:
        given = [t for t in (self.tol_abs, self.tol_pct) if t is not None]
        if len(given) != 1:
            raise ValueError("'approx' needs exactly one of 'tol_abs' or 'tol_pct'")
        if given[0] < 0:
            raise ValueError("tolerance must not be negative")
        return self

    def bounds(self) -> tuple[float, float]:
        tol = self.tol_abs if self.tol_abs is not None else abs(self.value) * self.tol_pct / 100
        return self.value - tol, self.value + tol


class CompareExpectation(StrictModel):
    op: Literal["eq", "ne", "le", "ge", "lt", "gt"]
    field: str
    value: int | float | str

    @model_validator(mode="after")
    def _numeric_for_ordering(self) -> CompareExpectation:
        if self.op not in ("eq", "ne") and isinstance(self.value, str):
            raise ValueError(f"'{self.op}' needs a numeric 'value'")
        return self


class RangeExpectation(StrictModel):
    op: Literal["in_range"]
    field: str
    low: float
    high: float

    @model_validator(mode="after")
    def _ordered(self) -> RangeExpectation:
        if self.low > self.high:
            raise ValueError("'in_range' needs low <= high")
        return self


class TextExpectation(StrictModel):
    op: Literal["contains", "matches"]
    field: str
    value: str

    @model_validator(mode="after")
    def _regex_compiles(self) -> TextExpectation:
        if self.op == "matches":
            try:
                re.compile(self.value)
            except re.error as exc:
                raise ValueError(f"'matches' value is not a valid regex: {exc}") from None
        return self


class NullExpectation(StrictModel):
    op: Literal["is_null", "not_null"]
    field: str


Expectation = Annotated[
    ApproxExpectation | CompareExpectation | RangeExpectation | TextExpectation | NullExpectation,
    Field(discriminator="op"),
]

# ------------------------------------------------------------------------------- stimulus


class DriveBase(StrictModel):
    op: Literal["drive"]
    id: Annotated[str, StringConstraints(pattern=ID_PATTERN)] | None = None
    pin: str


class DriveLevelStep(DriveBase):
    action: Literal["high", "low", "release"]


class DrivePulseStep(DriveBase):
    action: Literal["pulse"]
    width_ms: int
    level: Level


class DriveBounceStep(DriveBase):
    action: Literal["bounce"]
    count: int
    interval_us: int
    final_level: Level


DriveStep = Annotated[
    DriveLevelStep | DrivePulseStep | DriveBounceStep, Field(discriminator="action")
]


class WaitStep(StrictModel):
    op: Literal["wait"]
    id: Annotated[str, StringConstraints(pattern=ID_PATTERN)] | None = None
    ms: int


class UartSendStep(StrictModel):
    op: Literal["uart_send"]
    id: Annotated[str, StringConstraints(pattern=ID_PATTERN)] | None = None
    baud: int
    data: str | None = None
    hex: Annotated[str, StringConstraints(pattern=r"^([0-9A-Fa-f]{2})+$")] | None = None

    @model_validator(mode="after")
    def _one_payload(self) -> UartSendStep:
        if (self.data is None) == (self.hex is None):
            raise ValueError("'uart_send' needs exactly one of 'data' or 'hex'")
        return self

    def payload(self) -> bytes:
        return self.data.encode() if self.data is not None else bytes.fromhex(self.hex or "")


class DacSetStep(StrictModel):
    op: Literal["dac_set"]
    id: Annotated[str, StringConstraints(pattern=ID_PATTERN)] | None = None
    pin: str
    mv: int


RegisterKey = Annotated[str, StringConstraints(pattern=r"^(0x[0-9A-Fa-f]{1,2}|[0-9]{1,3})$")]


class I2cEmuStep(StrictModel):
    op: Literal["i2c_emu"]
    id: Annotated[str, StringConstraints(pattern=ID_PATTERN)] | None = None
    addr: int
    registers: dict[RegisterKey, int]

    def register_items(self) -> list[tuple[int, int]]:
        return sorted((int(k, 0), v) for k, v in self.registers.items())


# ---------------------------------------------------------------------------- measurement


class MeasureBase(StrictModel):
    op: Literal["measure"]
    id: Annotated[str, StringConstraints(pattern=ID_PATTERN)]
    requirement: str
    expect: list[Expectation]
    concurrent_with_next: bool = Field(
        default=False,
        description="Arm this measurement, run the next step(s) as stimulus, then collect.",
    )


class FreqDutyStep(MeasureBase):
    primitive: Literal["freq_duty"]
    pin: str
    window_ms: int


class EdgeDelayStep(MeasureBase):
    primitive: Literal["edge_delay"]
    from_pin: str
    from_edge: Edge
    to_pin: str
    to_edge: Edge
    timeout_ms: int


class LogicTraceStep(MeasureBase):
    primitive: Literal["logic_trace"]
    pin: str
    window_ms: int


class UartReadStep(MeasureBase):
    primitive: Literal["uart_read"]
    baud: int
    window_ms: int


class I2cLogStep(MeasureBase):
    primitive: Literal["i2c_log"]
    window_ms: int


class AnalogReadStep(MeasureBase):
    primitive: Literal["analog_read"]
    pin: str
    samples: int


MeasureStep = Annotated[
    FreqDutyStep | EdgeDelayStep | LogicTraceStep | UartReadStep | I2cLogStep | AnalogReadStep,
    Field(discriminator="primitive"),
]

Step = Annotated[
    DriveStep | WaitStep | UartSendStep | DacSetStep | I2cEmuStep | MeasureStep,
    Field(discriminator="op"),
]

MEASURE_TYPES = (
    FreqDutyStep,
    EdgeDelayStep,
    LogicTraceStep,
    UartReadStep,
    I2cLogStep,
    AnalogReadStep,
)
STIMULUS_TYPES = (DriveLevelStep, DrivePulseStep, DriveBounceStep, UartSendStep, DacSetStep)

#: Result fields each primitive returns. Expectations may only reference these.
PRIMITIVE_FIELDS: dict[str, tuple[str, ...]] = {
    "freq_duty": ("frequency_hz", "duty_pct", "edge_count"),
    "edge_delay": ("delay_ms", "to_edge_count"),
    "logic_trace": ("edge_count", "final_level", "edges_ms"),
    "uart_read": ("text", "byte_count", "framing_errors"),
    "i2c_log": ("read_count", "write_count", "transactions"),
    "analog_read": ("mean_mv", "min_mv", "max_mv"),
}

# ------------------------------------------------------------------------------------ plan


class Setup(StrictModel):
    reset: bool = True
    boot_wait_ms: int = 500


class NotGraded(StrictModel):
    requirement: str
    reason: str


class Plan(StrictModel):
    """A complete test plan for one assignment."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={"$schema": "https://json-schema.org/draft/2020-12/schema"},
    )

    schema_version: Literal["0.1"]
    assignment: Annotated[str, StringConstraints(pattern=r"^[a-z0-9_]+$")]
    description: str
    setup: Setup = Field(default_factory=Setup)
    steps: list[Step] = Field(min_length=1)
    not_graded: list[NotGraded] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)


def is_measure(step: Any) -> bool:
    return isinstance(step, MEASURE_TYPES)


def check_ids(step: MeasureBase) -> list[str]:
    """One check id per expectation: ``<step id>.<field>``, with ``#n`` for repeats."""
    seen: Counter[str] = Counter()
    ids = []
    for exp in step.expect:
        seen[exp.field] += 1
        n = seen[exp.field]
        ids.append(f"{step.id}.{exp.field}" + (f"#{n}" if n > 1 else ""))
    return ids


def unit_for(field: str) -> str:
    """Display unit derived from the field-name suffix (generic, not per assignment)."""
    for suffix, unit in (("_hz", "Hz"), ("_pct", "%"), ("_ms", "ms"), ("_mv", "mV")):
        if field.endswith(suffix):
            return unit
    return ""


# ------------------------------------------------------------------------- loading/errors


class PlanError(Exception):
    """A plan failed to load or validate. ``errors`` is a list of plain sentences."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


_TAGS = {
    "drive", "wait", "uart_send", "dac_set", "i2c_emu", "measure",
    "high", "low", "release", "pulse", "bounce",
    *PRIMITIVE_FIELDS,
    "approx", "eq", "ne", "le", "ge", "lt", "gt", "in_range", "contains", "matches",
    "is_null", "not_null",
}  # fmt: skip


def _format_loc(loc: tuple[Any, ...], raw: Any) -> str:
    parts: list[str] = []
    node = raw
    step_label = ""
    for i, item in enumerate(loc):
        if isinstance(item, int):
            parts.append(f"[{item}]")
            node = node[item] if isinstance(node, list) and item < len(node) else None
            if i == 1 and loc[0] == "steps" and isinstance(node, dict) and "id" in node:
                step_label = f"step '{node['id']}' "
        elif item in _TAGS and i > 0 and (isinstance(loc[i - 1], int) or loc[i - 1] in _TAGS):
            continue  # discriminator tag inserted by pydantic, not a real key
        else:
            parts.append(f".{item}" if parts else str(item))
            node = node.get(item) if isinstance(node, dict) else None
    return step_label + "(" + "".join(parts) + ")" if step_label else "".join(parts)


def format_validation_error(exc: ValidationError, raw: Any) -> list[str]:
    errors = []
    for err in exc.errors():
        msg = err["msg"].removeprefix("Value error, ")
        if err["type"] == "extra_forbidden":
            msg = "unknown field (not allowed by the schema)"
        where = _format_loc(tuple(err["loc"]), raw) or "plan"
        errors.append(f"{where}: {msg}")
    return errors


def parse_plan(raw: Any) -> Plan:
    try:
        return Plan.model_validate(raw)
    except ValidationError as exc:
        raise PlanError(format_validation_error(exc, raw)) from None


def load_plan(path: str | Path) -> Plan:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PlanError([f"{path.name}: not valid JSON ({exc})"]) from None
    return parse_plan(raw)


def export_schema() -> str:
    """The plan JSON Schema as text (stable, committed to ``schemas/plan.schema.json``)."""
    schema = Plan.model_json_schema()
    schema["title"] = "Autograder test plan"
    return json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
