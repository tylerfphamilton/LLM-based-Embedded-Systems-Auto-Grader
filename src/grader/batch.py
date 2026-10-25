"""Grade many simulated submissions and compute measurement-only benchmark metrics.

Ground truth comes from each scenario file and is used *only* here, after grading.
"""

from __future__ import annotations

import csv
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from grader.clock import FakeClock
from grader.fake_rig import FakeDevice, Scenario, load_scenario
from grader.feedback import FeedbackGenerator
from grader.flasher import NoopFlasher, Submission
from grader.pinmap import PinMap
from grader.plan import Plan
from grader.report import Report, write_reports
from grader.rig_profile import RigProfile
from grader.runner import run
from grader.transport import FakeTransport


def grade_scenario(
    plan: Plan,
    scenario: Scenario,
    *,
    pinmap: PinMap,
    rig_profile: RigProfile,
    feedback: FeedbackGenerator | None = None,
    plan_warnings: list[str] | None = None,
    repo_root: Path = Path("."),
) -> Report:
    """Run ``plan`` against the FakeRig for one scenario, with simulated time.

    A scenario's ``sketch`` (relative to ``repo_root``) becomes the submission's sketch
    directory, so feedback can read the student code. The FakeRig never flashes it.
    """
    if scenario.assignment is not None and scenario.assignment != plan.assignment:
        raise ValueError(
            f"scenario {scenario.submission!r} is for assignment {scenario.assignment!r}, "
            f"not {plan.assignment!r}"
        )
    clock = FakeClock(start=datetime.now(UTC))  # real start stamp, simulated elapsed time
    transport = FakeTransport(FakeDevice(scenario, clock))
    return run(
        plan,
        Submission(scenario.submission, repo_root / scenario.sketch if scenario.sketch else None),
        NoopFlasher(),
        transport,
        rig_profile,
        feedback,
        pinmap=pinmap,
        clock=clock,
        plan_warnings=plan_warnings,
    )


@dataclass(frozen=True)
class BatchRow:
    submission: str
    faulty: bool | None
    fault: str | None
    passed: int
    failed: int
    borderline: int
    errors: int
    report_dir: Path | None
    # LLM feedback call for this submission (at most one; none if nothing FAILed).
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    llm_latency_s: float = 0.0
    cost_usd: float | None = None  # None: no call, or prices not configured

    @property
    def flagged(self) -> bool:
        return self.failed > 0


@dataclass(frozen=True)
class BatchMetrics:
    submissions: int
    faulty: int
    correct: int
    detected: int  # faulty with >= 1 FAIL
    false_failures: int  # correct with >= 1 FAIL
    error_checks: int
    borderline_checks: int
    submissions_with_error: int
    submissions_with_borderline: int
    unlabelled: int
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    llm_latency_s: float = 0.0
    cost_usd: float | None = None  # None when no call had a known cost

    @property
    def detection_rate(self) -> float | None:
        return self.detected / self.faulty if self.faulty else None

    @property
    def false_failure_rate(self) -> float | None:
        return self.false_failures / self.correct if self.correct else None


def compute_metrics(rows: Iterable[BatchRow]) -> BatchMetrics:
    rows = list(rows)
    faulty = [r for r in rows if r.faulty is True]
    correct = [r for r in rows if r.faulty is False]
    costs = [r.cost_usd for r in rows if r.cost_usd is not None]
    return BatchMetrics(
        submissions=len(rows),
        faulty=len(faulty),
        correct=len(correct),
        detected=sum(r.flagged for r in faulty),
        false_failures=sum(r.flagged for r in correct),
        error_checks=sum(r.errors for r in rows),
        borderline_checks=sum(r.borderline for r in rows),
        submissions_with_error=sum(r.errors > 0 for r in rows),
        submissions_with_borderline=sum(r.borderline > 0 for r in rows),
        unlabelled=sum(r.faulty is None for r in rows),
        llm_calls=sum(r.llm_calls for r in rows),
        input_tokens=sum(r.input_tokens for r in rows),
        output_tokens=sum(r.output_tokens for r in rows),
        llm_latency_s=sum(r.llm_latency_s for r in rows),
        cost_usd=sum(costs) if costs else None,
    )


def run_batch(
    plan: Plan,
    scenario_paths: Iterable[Path],
    *,
    pinmap: PinMap,
    rig_profile: RigProfile,
    out_dir: Path | None = None,
    feedback: FeedbackGenerator | None = None,
    plan_warnings: list[str] | None = None,
    repo_root: Path = Path("."),
    cost_usd: Callable[[int, int], float | None] | None = None,
) -> tuple[list[BatchRow], BatchMetrics]:
    """Grade every scenario. ``cost_usd(input_tokens, output_tokens)`` prices LLM calls."""
    rows = []
    for path in sorted(scenario_paths):
        scenario = load_scenario(path)
        report = grade_scenario(
            plan,
            scenario,
            pinmap=pinmap,
            rig_profile=rig_profile,
            feedback=feedback,
            plan_warnings=plan_warnings,
            repo_root=repo_root,
        )
        report_dir = None
        if out_dir is not None:
            report_dir = out_dir / scenario.submission
            write_reports(report, report_dir)
        gt = scenario.ground_truth
        s = report.summary
        llm = report.llm
        rows.append(
            BatchRow(
                submission=scenario.submission,
                faulty=gt.faulty if gt else None,
                fault=gt.fault if gt else None,
                passed=s.PASS,
                failed=s.FAIL,
                borderline=s.BORDERLINE,
                errors=s.ERROR,
                report_dir=report_dir,
                llm_calls=1 if llm else 0,
                input_tokens=llm.input_tokens if llm else 0,
                output_tokens=llm.output_tokens if llm else 0,
                llm_latency_s=llm.latency_s if llm else 0.0,
                cost_usd=cost_usd(llm.input_tokens, llm.output_tokens)
                if llm and cost_usd
                else None,
            )
        )
    metrics = compute_metrics(rows)
    if out_dir is not None:
        write_summary_csv(rows, out_dir / "summary.csv", plan.assignment)
    return rows, metrics


CSV_HEADER = [
    "assignment",
    "submission",
    "ground_truth_faulty",
    "fault",
    "pass",
    "fail",
    "borderline",
    "error",
    "flagged",
    "llm_input_tokens",
    "llm_output_tokens",
    "llm_latency_s",
    "llm_cost_usd",
]


def write_summary_csv(rows: list[BatchRow], path: Path, assignment: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_HEADER)
        for r in rows:
            gt = "" if r.faulty is None else str(r.faulty).lower()
            flagged = str(r.flagged).lower()
            fault = r.fault or ""
            called = r.llm_calls > 0
            w.writerow(
                [
                    assignment,
                    r.submission,
                    gt,
                    fault,
                    r.passed,
                    r.failed,
                    r.borderline,
                    r.errors,
                    flagged,
                    r.input_tokens if called else "",
                    r.output_tokens if called else "",
                    f"{r.llm_latency_s:.3f}" if called else "",
                    f"{r.cost_usd:.6f}" if r.cost_usd is not None else "",
                ]
            )


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def format_table(rows: list[BatchRow], m: BatchMetrics) -> str:
    """Plain-ASCII table (safe on any Windows console code page)."""
    head = f"{'submission':<28} {'truth':<16} {'PASS':>4} {'FAIL':>4} {'BORD':>4} {'ERR':>4}"
    lines = [head, "-" * len(head)]
    for r in rows:
        truth = (
            "unlabelled" if r.faulty is None else (r.fault or "faulty") if r.faulty else "correct"
        )
        lines.append(
            f"{r.submission:<28} {truth:<16} {r.passed:>4} {r.failed:>4} "
            f"{r.borderline:>4} {r.errors:>4}"
        )
    lines += [
        "",
        f"Bug detection rate : {_pct(m.detection_rate)}  ({m.detected}/{m.faulty} faulty "
        "submissions with >= 1 FAIL)",
        f"False failure rate : {_pct(m.false_failure_rate)}  ({m.false_failures}/{m.correct} "
        "correct submissions with >= 1 FAIL)",
        f"ERROR checks       : {m.error_checks}  (in {m.submissions_with_error} submission(s))",
        f"BORDERLINE checks  : {m.borderline_checks}  (in {m.submissions_with_borderline} "
        "submission(s))",
    ]
    if m.unlabelled:
        lines.append(f"Unlabelled         : {m.unlabelled} (no ground_truth; excluded from rates)")
    if m.llm_calls:
        lines.append(
            f"LLM feedback       : {m.llm_calls} call(s), {m.input_tokens} input + "
            f"{m.output_tokens} output tokens, {m.llm_latency_s:.1f} s"
        )
        if m.cost_usd is None:
            lines.append("LLM cost           : unknown (set price_per_mtok in config/llm.yaml)")
        else:
            lines.append(
                f"LLM cost           : ${m.cost_usd:.4f} total, "
                f"${m.cost_usd / m.llm_calls:.4f} per call (list price)"
            )
    return "\n".join(lines)
