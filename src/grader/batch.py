"""Grade many simulated submissions and compute measurement-only benchmark metrics.

Ground truth comes from each scenario file and is used *only* here, after grading.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
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
) -> Report:
    """Run ``plan`` against the FakeRig for one scenario, with simulated time."""
    if scenario.assignment is not None and scenario.assignment != plan.assignment:
        raise ValueError(
            f"scenario {scenario.submission!r} is for assignment {scenario.assignment!r}, "
            f"not {plan.assignment!r}"
        )
    clock = FakeClock(start=datetime.now(UTC))  # real start stamp, simulated elapsed time
    transport = FakeTransport(FakeDevice(scenario, clock))
    return run(
        plan,
        Submission(scenario.submission),
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
) -> tuple[list[BatchRow], BatchMetrics]:
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
        )
        report_dir = None
        if out_dir is not None:
            report_dir = out_dir / scenario.submission
            write_reports(report, report_dir)
        gt = scenario.ground_truth
        s = report.summary
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
    return "\n".join(lines)
