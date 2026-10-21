"""Report model plus JSON (machine) and Markdown (student) renderers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from grader.compare import Verdict, fmt_measured

REPORT_VERSION = "0.1"


class CheckResult(BaseModel):
    id: str
    step_id: str | None
    requirement: str
    primitive: str | None = None
    field: str | None = None
    op: str | None = None
    expected: Any = None
    expected_text: str = ""
    tolerance: dict[str, float] | None = None
    measured: Any = None
    verdict: Verdict
    reason: str
    feedback: str | None = None


class LogEntry(BaseModel):
    t_ms: float
    dir: Literal["tx", "rx", "debug", "note"]
    line: str


class FlashInfo(BaseModel):
    ok: bool
    stage: str
    student_fault: bool = False
    log: str = ""


class RigInfo(BaseModel):
    transport: str
    flasher: str
    profile: str


class Summary(BaseModel):
    total: int = 0
    PASS: int = 0
    FAIL: int = 0
    BORDERLINE: int = 0
    ERROR: int = 0
    NOT_GRADED: int = 0

    @property
    def graded(self) -> int:
        return self.total - self.NOT_GRADED


class Report(BaseModel):
    report_version: str = REPORT_VERSION
    assignment: str
    plan_description: str
    plan_schema_version: str
    submission: str
    started_at: str
    finished_at: str
    rig: RigInfo
    flash: FlashInfo
    assumptions: list[str] = Field(default_factory=list)
    rig_faults: list[str] = Field(default_factory=list)
    plan_warnings: list[str] = Field(default_factory=list)  # provenance (meta file)
    checks: list[CheckResult] = Field(default_factory=list)
    command_log: list[LogEntry] = Field(default_factory=list)
    summary: Summary = Field(default_factory=Summary)

    def verdicts(self) -> dict[str, Verdict]:
        return {c.id: c.verdict for c in self.checks if c.verdict != Verdict.NOT_GRADED}


def summarize(checks: list[CheckResult]) -> Summary:
    s = Summary(total=len(checks))
    for c in checks:
        setattr(s, c.verdict.value, getattr(s, c.verdict.value) + 1)
    return s


# --------------------------------------------------------------------------- markdown

_BADGE = {
    Verdict.PASS: "✅ PASS",
    Verdict.FAIL: "❌ FAIL",
    Verdict.BORDERLINE: "⚠️ BORDERLINE",
    Verdict.ERROR: "🛠️ RIG ERROR",
}
FEEDBACK_PLACEHOLDER = "_Detailed feedback is not available yet._"


_MD_SPECIAL = "\\`*_[]<>|#"


def md_escape(text: str) -> str:
    """Escape Markdown so regexes and student output render literally."""
    return "".join("\\" + ch if ch in _MD_SPECIAL else ch for ch in text).replace("\n", " ")


def _cell(text: str) -> str:
    return md_escape(text)


def _measured(c: CheckResult) -> str:
    if c.verdict == Verdict.ERROR and c.measured is None:
        return "—"
    return fmt_measured(c.measured, c.field or "")


def render_markdown(r: Report) -> str:
    graded = [c for c in r.checks if c.verdict != Verdict.NOT_GRADED]
    s = r.summary
    out = [
        f"# Autograder report: {r.assignment}",
        "",
        f"**Submission:** `{r.submission}`  ",
        f"**Result: {s.PASS} of {s.graded} checks passed** · {s.FAIL} failed · "
        f"{s.BORDERLINE} borderline · {s.ERROR} could not be measured",
        "",
        f"> {r.plan_description}",
        "",
    ]
    if not r.flash.ok:
        what = "did not compile" if r.flash.student_fault else "could not be uploaded"
        out += [
            f"**Your sketch {what}, so no checks were run.**",
            "",
            "```",
            r.flash.log,
            "```",
            "",
        ]
    if graded:
        out += [
            "| Requirement | Quantity | Expected | Measured | Verdict |",
            "|---|---|---|---|---|",
        ]
        for c in graded:
            out.append(
                f"| {_cell(c.requirement)} | `{c.field}` | {_cell(c.expected_text)} | "
                f"{_cell(_measured(c))} | {_BADGE[c.verdict]} |"
            )
        out.append("")

    failed = [c for c in graded if c.verdict == Verdict.FAIL]
    if failed:
        out += ["## What to fix", ""]
        for c in failed:
            out += [
                f"### ❌ {md_escape(c.requirement)} (`{c.field}`)",
                "",
                f"- **Why:** {md_escape(c.reason)}",
                f"- **Feedback:** {c.feedback or FEEDBACK_PLACEHOLDER}",
                "",
            ]

    borderline = [c for c in graded if c.verdict == Verdict.BORDERLINE]
    if borderline:
        out += [
            "## Borderline: a TA will review these",
            "",
            "These values are so close to a limit that the test equipment cannot reliably "
            "tell pass from fail.",
            "",
        ]
        out += [
            f"- **{md_escape(c.requirement)}** (`{c.field}`): {md_escape(c.reason)}"
            for c in borderline
        ]
        out.append("")

    errors = [c for c in graded if c.verdict == Verdict.ERROR]
    if errors:
        out += [
            "## Not measured: test equipment problem",
            "",
            "These checks could not be measured because of a problem with the test rig. "
            "They do **not** count against you; they will be re-run.",
            "",
        ]
        out += [f"- **{md_escape(c.requirement)}** (`{c.field}`)" for c in errors]
        out.append("")

    not_graded = [c for c in r.checks if c.verdict == Verdict.NOT_GRADED]
    if not_graded:
        out += ["## Not graded automatically", ""]
        out += [f"- **{md_escape(c.requirement)}**: {md_escape(c.reason)}" for c in not_graded]
        out.append("")

    if r.assumptions:
        out += ["## Assumptions the grader made", ""]
        out += [f"- {md_escape(a)}" for a in r.assumptions]
        out.append("")
    return "\n".join(out)


def write_reports(report: Report, directory: str | Path) -> tuple[Path, Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "report.json"
    md_path = directory / "report.md"
    json_path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path
