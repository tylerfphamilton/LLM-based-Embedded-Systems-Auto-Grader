"""FakeRig: a simulated measuring board for one simulated submission.

A scenario YAML gives canned measurement replies. The FakeDevice parses each request with
the real protocol parser and answers with real protocol lines, so it sits *below* the
protocol layer. ``ground_truth`` and ``expected_verdicts`` are for batch metrics and
tests only; the runner never sees them.
"""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from grader.clock import FakeClock
from grader.protocol import (
    Arm,
    Collect,
    Command,
    Debug,
    Err,
    Ok,
    ProtocolError,
    format_response,
    parse_command,
    parse_response,
)

VerdictName = Literal["PASS", "FAIL", "BORDERLINE", "ERROR", "NOT_GRADED"]
MatchValue = str | int | float


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _check_err_line(line: str) -> str:
    try:
        resp = parse_response(line)
    except ProtocolError as exc:
        raise ValueError(f"not a valid protocol line: {exc}") from None
    if not isinstance(resp, Err):
        raise ValueError(f"expected an 'ERR <CODE> ...' line, got {line!r}")
    return line


class GroundTruth(_Model):
    faulty: bool
    fault: str | None = None


class NoiseField(_Model):
    abs: float = 0.0
    pct: float = 0.0


class Noise(_Model):
    seed: int
    fields: dict[str, NoiseField] = Field(default_factory=dict)


class ResponseRule(_Model):
    match: dict[str, MatchValue]
    reply: dict[str, Any] | None = None
    replies: list[dict[str, Any]] | None = None
    error: str | None = None

    @model_validator(mode="after")
    def _one_kind(self) -> ResponseRule:
        if sum(x is not None for x in (self.reply, self.replies, self.error)) != 1:
            raise ValueError("a response rule needs exactly one of reply, replies or error")
        if self.error is not None:
            _check_err_line(self.error)
        if "cmd" not in self.match:
            raise ValueError("a response rule's match must include 'cmd'")
        return self


class FailRule(_Model):
    """Make a command (stimulus or measurement) fail: reply with ``error`` or stay silent."""

    cmd: str
    match: dict[str, MatchValue] = Field(default_factory=dict)
    error: str | None = None
    silent: bool = False

    @model_validator(mode="after")
    def _one_kind(self) -> FailRule:
        if (self.error is not None) == self.silent:
            raise ValueError("fail_command needs exactly one of 'error' or 'silent: true'")
        if self.error is not None:
            _check_err_line(self.error)
        return self


class Default(_Model):
    error: str = "ERR BADCMD no scenario match"

    @field_validator("error")
    @classmethod
    def _valid(cls, v: str) -> str:
        return _check_err_line(v)


class Scenario(_Model):
    submission: str
    assignment: str | None = None
    sketch: Path | None = None  # student sketch directory, relative to the repo root
    description: str = ""
    ground_truth: GroundTruth | None = None
    noise: Noise | None = None
    debug_lines: bool = False
    responses: list[ResponseRule] = Field(default_factory=list)
    fail_command: FailRule | list[FailRule] | None = None
    default: Default = Field(default_factory=Default)
    expected_verdicts: dict[str, VerdictName] = Field(default_factory=dict)

    @property
    def fail_rules(self) -> list[FailRule]:
        if self.fail_command is None:
            return []
        return self.fail_command if isinstance(self.fail_command, list) else [self.fail_command]


def load_scenario(path: str | Path) -> Scenario:
    return Scenario.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))


def _matches(match: dict[str, MatchValue], fields: dict[str, str]) -> bool:
    return all(fields.get(k.lower()) == str(v).lower() for k, v in match.items())


class FakeDevice:
    """Speaks the measuring-board protocol, answering from a scenario."""

    def __init__(self, scenario: Scenario, clock: FakeClock | None = None):
        self.scenario = scenario
        self._clock = clock
        self._rng = random.Random(scenario.noise.seed) if scenario.noise else None
        self._cursor = [0] * len(scenario.responses)
        self._slots: dict[int, tuple[list[str], float]] = {}
        self._next_slot = 0
        self.received: list[str] = []

    # -- LineDevice -------------------------------------------------------------------
    def handle(self, line: str) -> list[str]:
        self.received.append(line)
        try:
            cmd = parse_command(line)
        except ProtocolError as exc:
            return [format_response(Err("BADCMD", str(exc)))]
        replies = self._respond(cmd)
        if self.scenario.debug_lines:
            replies = [format_response(Debug(f"fake rig got {line}")), *replies]
        return replies

    # -- internals ----------------------------------------------------------------------
    def _advance(self, ms: float) -> None:
        if self._clock is not None:
            self._clock.advance(ms / 1000)

    def _respond(self, cmd: Command) -> list[str]:
        if isinstance(cmd, Arm):
            failed = self._failure(cmd)
            if failed is not None:
                return failed
            slot = self._next_slot
            self._next_slot += 1
            # The result is decided now (the measurement starts now); COLLECT returns it.
            self._slots[slot] = (self._reply(cmd.inner), cmd.inner.duration_ms())
            return [format_response(Ok({"slot": slot}))]
        if isinstance(cmd, Collect):
            failed = self._failure(cmd)
            if failed is not None:
                return failed
            if cmd.slot not in self._slots:
                return [format_response(Err("NOSLOT", f"slot {cmd.slot} is not armed"))]
            lines, duration = self._slots.pop(cmd.slot)
            self._advance(duration)
            return lines
        self._advance(cmd.duration_ms())
        return self._reply(cmd)

    def _failure(self, cmd: Command) -> list[str] | None:
        fields = cmd.match_fields()
        for rule in self.scenario.fail_rules:
            if _matches({"cmd": rule.cmd, **rule.match}, fields):
                return [] if rule.silent else [rule.error or ""]
        return None

    def _reply(self, cmd: Command) -> list[str]:
        """Reply lines for a plain (non-ARM/COLLECT) command, without touching the clock."""
        failed = self._failure(cmd)
        if failed is not None:
            return failed
        fields = cmd.match_fields()
        if not cmd.MEASUREMENT:
            return ["OK"]
        return [self._measure(cmd, fields)]

    def _measure(self, cmd: Command, fields: dict[str, str]) -> str:
        for i, rule in enumerate(self.scenario.responses):
            if not _matches(rule.match, fields):
                continue
            if rule.error is not None:
                return rule.error
            if rule.reply is not None:
                values = dict(rule.reply)
            else:
                assert rule.replies is not None
                if self._cursor[i] >= len(rule.replies):
                    return format_response(
                        Err("BADCMD", f"scenario replies exhausted for {cmd.to_line()}")
                    )
                values = dict(rule.replies[self._cursor[i]])
                self._cursor[i] += 1
            return format_response(Ok(self._add_noise(values)))
        return self.scenario.default.error

    def _add_noise(self, values: dict[str, Any]) -> dict[str, Any]:
        noise = self.scenario.noise
        if noise is None or self._rng is None:
            return values
        for name in sorted(noise.fields):  # sorted: RNG draws in a fixed order
            v = values.get(name)
            if isinstance(v, int | float) and not isinstance(v, bool):
                spec = noise.fields[name]
                err = spec.abs + abs(v) * spec.pct / 100
                values[name] = round(float(v) + self._rng.uniform(-err, err), 6)
        return values
