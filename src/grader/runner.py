"""Execute one test plan against one rig for one submission.

Nothing here knows about any particular assignment: the plan drives everything.
"""

from __future__ import annotations

from typing import Any

from grader.clock import Clock, SystemClock
from grader.compare import Measurement, Outcome, Verdict, compare, describe, tolerance
from grader.feedback import FeedbackGenerator, FeedbackResult, NullFeedback
from grader.flasher import Flasher, FlashResult, Submission
from grader.pinmap import PinMap
from grader.plan import (
    ApproxExpectation,
    MeasureBase,
    NullExpectation,
    Plan,
    PlanError,
    RangeExpectation,
    check_ids,
    is_measure,
)
from grader.protocol import (
    Arm,
    Collect,
    Command,
    Debug,
    Err,
    Ok,
    ProtocolError,
    Reset,
    Wait,
    command_for_step,
    parse_response,
)
from grader.report import CheckResult, FlashInfo, LogEntry, Report, RigInfo, summarize
from grader.rig_profile import RigProfile
from grader.transport import Transport, TransportError
from grader.validate import validate_plan

MAX_DEBUG_LINES = 200  # per reply; protects against a board that only chatters


class RigFault(Exception):
    """The rig did not produce a valid result (ERR reply, timeout, malformed line)."""


class RigClient:
    """Sends commands, reads exactly one reply each, and logs everything."""

    def __init__(self, transport: Transport, profile: RigProfile, clock: Clock):
        self.transport, self.profile, self.clock = transport, profile, clock
        self.log: list[LogEntry] = []
        self._t0 = clock.monotonic()

    def note(self, direction: str, line: str) -> None:
        t_ms = round((self.clock.monotonic() - self._t0) * 1000, 3)
        self.log.append(LogEntry(t_ms=t_ms, dir=direction, line=line))  # type: ignore[arg-type]

    def request(self, cmd: Command, duration_ms: float | None = None) -> Ok:
        line = cmd.to_line()
        dur = cmd.duration_ms() if duration_ms is None else duration_ms
        timeout_s = (
            self.profile.timeouts.command_s + self.profile.timeouts.slack_factor * dur / 1000
        )
        self.note("tx", line)
        try:
            self.transport.send_line(line)
            for _ in range(MAX_DEBUG_LINES):
                raw = self.transport.read_line(timeout_s)
                is_debug = raw.startswith("#")
                self.note("debug" if is_debug else "rx", raw)
                resp = parse_response(raw)
                if isinstance(resp, Debug):
                    continue
                if isinstance(resp, Err):
                    raise RigFault(f"{line} -> ERR {resp.code} {resp.message}".rstrip())
                return resp
            raise RigFault(f"{line} -> more than {MAX_DEBUG_LINES} debug lines, no reply")
        except TransportError as exc:
            raise RigFault(f"{line} -> {exc}") from None
        except ProtocolError as exc:
            raise RigFault(f"{line} -> malformed reply: {exc}") from None

    def measure(self, cmd: Command) -> Measurement:
        try:
            return Measurement.ok(self.request(cmd).fields)
        except RigFault as exc:
            return Measurement.rig_error(str(exc))


def _step_name(step: Any, index: int) -> str:
    return f"'{step.id}'" if getattr(step, "id", None) else f"#{index + 1} ({step.op})"


def _expected_value(exp: Any) -> Any:
    if isinstance(exp, RangeExpectation):
        return [exp.low, exp.high]
    if isinstance(exp, NullExpectation):
        return None
    return exp.value


def _checks_for(step: MeasureBase, m: Measurement, profile: RigProfile) -> list[CheckResult]:
    results = []
    for cid, exp in zip(check_ids(step), step.expect, strict=True):
        out: Outcome = compare(exp, m, profile)
        results.append(
            CheckResult(
                id=cid,
                step_id=step.id,
                requirement=step.requirement,
                primitive=step.primitive,  # type: ignore[attr-defined]
                field=exp.field,
                op=exp.op,
                expected=_expected_value(exp),
                expected_text=describe(exp),
                tolerance=tolerance(exp) if isinstance(exp, ApproxExpectation) else None,
                measured=out.measured,
                verdict=out.verdict,
                reason=out.reason,
            )
        )
    return results


def _all_checks(plan: Plan, verdict: Verdict, reason: str) -> list[CheckResult]:
    """Every check with the same verdict, used when nothing could be measured."""
    m = Measurement.rig_error(reason)
    out = []
    for step in plan.steps:
        if is_measure(step):
            for c in _checks_for(step, m, RigProfile()):
                out.append(c.model_copy(update={"verdict": verdict, "reason": reason}))
    return out


def _execute(plan: Plan, rig: RigClient, faults: list[str]) -> list[CheckResult]:
    checks: list[CheckResult] = []
    steps = plan.steps
    i = 0
    while i < len(steps):
        step = steps[i]
        if is_measure(step) and step.concurrent_with_next:
            # Arm every consecutive concurrent measure, run the stimulus, then collect.
            group: list[MeasureBase] = []
            while is_measure(steps[i]) and steps[i].concurrent_with_next:
                group.append(steps[i])
                i += 1
            stimulus = steps[i]
            i += 1
            armed: list[tuple[MeasureBase, Command, int | Measurement]] = []
            for m_step in group:
                cmd = command_for_step(m_step)
                try:
                    slot = rig.request(Arm(cmd)).fields.get("slot")
                    if not isinstance(slot, int):
                        raise RigFault(f"ARM reply has no integer 'slot': {slot!r}")
                    armed.append((m_step, cmd, slot))
                except RigFault as exc:
                    armed.append((m_step, cmd, Measurement.rig_error(str(exc))))
            stim_fault: str | None = None
            try:
                rig.request(command_for_step(stimulus))
            except RigFault as exc:
                stim_fault = f"stimulus step {_step_name(stimulus, i - 1)} failed: {exc}"
                faults.append(stim_fault)
            for m_step, cmd, slot_or_m in armed:
                if isinstance(slot_or_m, Measurement):
                    m = slot_or_m
                else:
                    try:
                        m = Measurement.ok(
                            rig.request(Collect(slot_or_m), duration_ms=cmd.duration_ms()).fields
                        )
                    except RigFault as exc:
                        m = Measurement.rig_error(str(exc))
                    if stim_fault is not None:
                        m = Measurement.rig_error(stim_fault)
                checks += _checks_for(m_step, m, rig.profile)
            continue

        if is_measure(step):
            checks += _checks_for(step, rig.measure(command_for_step(step)), rig.profile)
        else:
            try:
                rig.request(command_for_step(step))
            except RigFault as exc:
                # Continue: later checks may still be valid; the report flags the fault.
                faults.append(f"step {_step_name(step, i)} failed: {exc}")
                rig.note("note", faults[-1])
        i += 1
    return checks


def run(
    plan: Plan,
    submission: Submission,
    flasher: Flasher,
    transport: Transport,
    rig_profile: RigProfile,
    feedback: FeedbackGenerator | None = None,
    *,
    pinmap: PinMap,
    clock: Clock | None = None,
    plan_warnings: list[str] | None = None,
) -> Report:
    """Grade one submission. Raises PlanError if the plan is invalid."""
    errors = validate_plan(plan, pinmap)
    if errors:
        raise PlanError(errors)
    feedback = feedback or NullFeedback()
    clock = clock or SystemClock()
    started = clock.wall().isoformat()
    rig = RigClient(transport, rig_profile, clock)
    faults: list[str] = []

    flash: FlashResult = flasher.flash(submission)
    if not flash.ok:
        if flash.student_fault:
            checks = _all_checks(plan, Verdict.FAIL, "the sketch did not compile")
        else:
            reason = f"rig error: flashing failed at the {flash.stage} stage"
            checks = _all_checks(plan, Verdict.ERROR, reason)
            faults.append(reason)
    else:
        try:
            if plan.setup.reset:
                rig.request(Reset())
            if plan.setup.boot_wait_ms > 0:
                rig.request(Wait(plan.setup.boot_wait_ms))
        except RigFault as exc:
            faults.append(f"setup failed: {exc}")
            checks = _all_checks(plan, Verdict.ERROR, f"rig error: setup failed: {exc}")
        else:
            checks = _execute(plan, rig, faults)

    # Verdicts are final here. One feedback call per submission, and only if something
    # FAILed; BORDERLINE/ERROR/PASS never get feedback text.
    failed = [c for c in checks if c.verdict == Verdict.FAIL]
    fb = feedback.explain_all(checks, plan, submission, rig.log) if failed else FeedbackResult()
    for c in failed:
        c.feedback = fb.texts.get(c.id)
        c.code_location = fb.code_locations.get(c.id)
    for n, ng in enumerate(plan.not_graded, start=1):
        checks.append(
            CheckResult(
                id=f"not_graded.{n}",
                step_id=None,
                requirement=ng.requirement,
                verdict=Verdict.NOT_GRADED,
                reason=ng.reason,
            )
        )

    return Report(
        assignment=plan.assignment,
        plan_description=plan.description,
        plan_schema_version=plan.schema_version,
        submission=submission.id,
        started_at=started,
        finished_at=clock.wall().isoformat(),
        rig=RigInfo(transport=transport.describe(), flasher=flasher.kind, profile=rig_profile.name),
        flash=FlashInfo(
            ok=flash.ok, stage=flash.stage, student_fault=flash.student_fault, log=flash.log
        ),
        assumptions=plan.assumptions,
        rig_faults=faults,
        plan_warnings=list(plan_warnings or []),
        llm=fb.llm,
        llm_raw=fb.raw,
        checks=checks,
        command_log=rig.log,
        summary=summarize(checks),
    )
