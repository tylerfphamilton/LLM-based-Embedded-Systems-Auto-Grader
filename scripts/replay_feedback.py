"""Re-run LLM feedback on the measurements of an earlier hardware run, without the rig.

Reads <reports>/<id>/report.json, keeps every verdict, measurement and command-log line,
asks the LLM again (with the current feedback prompt) to explain the FAIL checks, and
writes new reports plus replay_summary.csv. Use it to compare prompt versions on
identical data. Use the same plan the earlier run used.

    python scripts/replay_feedback.py --plan plans/pwm_1khz_llm_v2.json ^
        --reports out/pwm_hw_new_tests --submissions benchmark/pwm_1khz --out out/replay
    python scripts/replay_feedback.py ... submission_05 submission_06    # only these

Needs ANTHROPIC_API_KEY: one LLM call per submission that has a FAIL check.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from grader.batch import load_labels
from grader.compare import Verdict
from grader.feedback import FeedbackGenerator, LLMFeedback
from grader.flasher import Submission
from grader.llm import AnthropicClient, LLMConfig, LLMError, load_llm_config, require_api_key
from grader.plan import Plan, load_plan
from grader.report import Report, write_reports

COLUMNS = [
    "id", "fault", "failed_checks", "possible_causes", "same_cause_as",
    "input_tokens", "output_tokens", "latency_s", "cost_usd", "llm_error",
]  # fmt: skip


def replay(
    plan: Plan,
    report_paths: list[Path],
    submissions: Path,
    out_dir: Path,
    feedback: FeedbackGenerator,
    cfg: LLMConfig,
) -> list[dict]:
    labels = load_labels(submissions)
    step_ids = {s.id for s in plan.steps}
    rows = []
    for path in report_paths:
        report = Report.model_validate_json(path.read_text(encoding="utf-8"))
        failed = [c for c in report.checks if c.verdict == Verdict.FAIL]
        if not failed:
            continue
        sid = path.parent.name  # the batch's output folder = the sketch folder name
        if unknown := {c.step_id for c in failed if c.step_id} - step_ids:
            print(f"warning: {sid}: steps {sorted(unknown)} are not in {plan.description!r}")
        sub = Submission(sid, submissions / sid)
        fb = feedback.explain_all(report.checks, plan, sub, report.command_log)
        for c in failed:  # same as runner.py
            c.feedback = fb.texts.get(c.id)
            c.code_location = fb.code_locations.get(c.id)
            c.cause_found = fb.cause_found.get(c.id)
            c.same_cause_as = fb.same_cause_as.get(c.id)
        report.llm, report.llm_raw = fb.llm, fb.raw
        write_reports(report, out_dir / sid)
        info, label = fb.llm, labels.get(sid)
        cost = cfg.cost_usd(info.input_tokens, info.output_tokens) if info else None
        rows.append(
            {
                "id": sid,
                "fault": (label.fault or "") if label else "",
                "failed_checks": len(failed),
                "possible_causes": sum(c.cause_found is False for c in failed),
                "same_cause_as": sum(c.same_cause_as is not None for c in failed),
                "input_tokens": info.input_tokens if info else 0,
                "output_tokens": info.output_tokens if info else 0,
                "latency_s": round(info.latency_s, 1) if info else 0.0,
                "cost_usd": round(cost, 4) if cost is not None else "",
                "llm_error": (info.error or "") if info else "",
            }
        )
        r = rows[-1]
        print(
            f"{sid}: {r['failed_checks']} failed, {r['possible_causes']} possible-causes, "
            f"{r['output_tokens']} output tokens, {r['latency_s']} s {r['llm_error']}"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "replay_summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--plan", type=Path, required=True, help="the plan the earlier run used")
    ap.add_argument("--reports", type=Path, required=True, help="earlier batch output folder")
    ap.add_argument("--submissions", type=Path, required=True, help="the sketch folders")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--llm-config", type=Path, default=Path("config/llm.yaml"))
    ap.add_argument("ids", nargs="*", help="only these submissions (default: all)")
    args = ap.parse_args(argv)

    cfg = load_llm_config(args.llm_config)
    try:
        cfg.check()
        require_api_key()
    except LLMError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    paths = sorted(args.reports.glob("*/report.json"))
    if args.ids:
        paths = [p for p in paths if p.parent.name in args.ids]
    if not paths:
        print(f"error: no matching */report.json in {args.reports}", file=sys.stderr)
        return 2
    feedback = LLMFeedback(AnthropicClient.from_config(cfg), cfg)
    rows = replay(load_plan(args.plan), paths, args.submissions, args.out, feedback, cfg)
    cost = sum(r["cost_usd"] or 0 for r in rows)
    print(f"{len(rows)} submissions replayed, ${cost:.3f}; see {args.out / 'replay_summary.csv'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
