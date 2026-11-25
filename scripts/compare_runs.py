"""Compare a hardware batch with the code-only baseline (D66), per submission.

    python scripts/compare_runs.py --hw out/btn17_final_button_toggle_opus_c --code out/code_btn

Reads both runs' ``summary.csv`` and prints one row per submission (truth, hardware flagged,
code flagged, code UNSURE, agree), then both detection and false-failure rates, the
submissions where the runs disagree, and each run's LLM cost per graded submission.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

HEADER = ["submission", "truth", "hardware_flagged", "code_flagged", "code_unsure", "agree"]


def read_summary(folder: Path) -> dict[str, dict[str, str]]:
    with (folder / "summary.csv").open(encoding="utf-8", newline="") as fh:
        return {row["submission"]: row for row in csv.DictReader(fh)}


def _truth(row: dict[str, str]) -> str:
    faulty = row.get("ground_truth_faulty", "")
    if faulty == "":
        return "unlabelled"
    return (row.get("fault") or "faulty") if faulty == "true" else "correct"


def compare(hw: dict[str, dict], code: dict[str, dict]) -> dict:
    """The comparison table and everything printed under it."""
    both = sorted(hw.keys() & code.keys())
    table = []
    for sub in both:
        h, c = hw[sub]["flagged"] == "true", code[sub]["flagged"] == "true"
        truth = _truth(hw[sub])
        if truth == "unlabelled":
            truth = _truth(code[sub])
        table.append(
            {"submission": sub, "truth": truth, "hardware_flagged": h, "code_flagged": c,
             "code_unsure": int(code[sub].get("unsure") or 0), "agree": h == c}
        )  # fmt: skip
    return {
        "table": table,
        "rates": {run: _rates(table, f"{run}_flagged") for run in ("hardware", "code")},
        "disagree": [r["submission"] for r in table if not r["agree"]],
        "only_hw": sorted(hw.keys() - code.keys()),
        "only_code": sorted(code.keys() - hw.keys()),
    }


def _rates(table: list[dict], key: str) -> tuple[float | None, float | None]:
    faulty = [r for r in table if r["truth"] not in ("correct", "unlabelled")]
    correct = [r for r in table if r["truth"] == "correct"]
    det = sum(r[key] for r in faulty) / len(faulty) if faulty else None
    ff = sum(r[key] for r in correct) / len(correct) if correct else None
    return det, ff


def cost_per_submission(rows: dict[str, dict], extra: float = 0.0) -> str:
    costs = [float(r["llm_cost_usd"]) for r in rows.values() if r.get("llm_cost_usd")]
    if not rows or (not costs and not extra):
        return "n/a (no prices in summary.csv)"
    note = f", {len(costs)} of {len(rows)} rows priced" if len(costs) < len(rows) else ""
    total = sum(costs) + extra
    return f"${total / len(rows):.4f} per graded submission (${total:.4f} total{note})"


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def format_report(result: dict, hw: dict, code: dict, req_cost: float) -> str:
    yn = {True: "yes", False: "no"}
    head = f"{'submission':<24} {'truth':<18} {'hw flagged':>10} {'code flagged':>12} "
    head += f"{'code UNSURE':>11} {'agree':>5}"
    lines = [head, "-" * len(head)]
    for r in result["table"]:
        lines.append(
            f"{r['submission']:<24} {r['truth']:<18} {yn[r['hardware_flagged']]:>10} "
            f"{yn[r['code_flagged']]:>12} {r['code_unsure']:>11} {yn[r['agree']]:>5}"
        )
    lines.append("")
    for run in ("hardware", "code"):
        det, ff = result["rates"][run]
        lines.append(f"{run:<8}: detection {_pct(det)}, false failures {_pct(ff)}")
    agree = sum(r["agree"] for r in result["table"])
    lines.append(f"agree   : {agree}/{len(result['table'])}")
    lines.append(f"disagree: {', '.join(result['disagree']) or 'none'}")
    if result["only_hw"]:
        lines.append(f"only in the hardware run: {', '.join(result['only_hw'])}")
    if result["only_code"]:
        lines.append(f"only in the code run    : {', '.join(result['only_code'])}")
    lines.append(f"cost hardware: {cost_per_submission(hw)}  (feedback calls only)")
    lines.append(f"cost code    : {cost_per_submission(code, req_cost)}  (incl. requirements)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--hw", type=Path, required=True, help="hardware batch output folder")
    ap.add_argument("--code", type=Path, required=True, help="grader code-grade output folder")
    ap.add_argument("--csv", type=Path, help="also save the table as CSV")
    args = ap.parse_args(argv)
    try:
        hw, code = read_summary(args.hw), read_summary(args.code)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    req_cost = 0.0
    req_file = args.code / "requirements.json"
    if req_file.exists():
        doc = json.loads(req_file.read_text(encoding="utf-8"))
        req_cost = 0.0 if "reused_from" in doc else float(doc.get("cost_usd") or 0.0)
    result = compare(hw, code)
    print(format_report(result, hw, code, req_cost))
    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with args.csv.open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=HEADER)
            w.writeheader()
            w.writerows({**r, **{k: str(r[k]).lower() for k in HEADER[2:4] + HEADER[5:]}}
                        for r in result["table"])  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())
