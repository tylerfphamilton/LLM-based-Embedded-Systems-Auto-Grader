"""Code-only baseline (D66): an LLM grades each sketch from the handout and its code alone.

No plan, no rig, no measurement. The output is only compared with the hardware batches; it
never feeds into hardware grading.
"""

from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from grader.batch import BatchMetrics, BatchRow, _pct, compute_metrics
from grader.fake_rig import GroundTruth
from grader.feedback import Redactor, read_sources
from grader.flasher import Submission
from grader.llm import LLMClient, LLMConfig, LLMError, LLMRequest, NoToolCallError, load_prompt
from grader.planner import PlanResult, file_sha256, repair_loop
from grader.report import md_escape

BOARD = "Arduino Nano 33 BLE Sense, Arduino mbed core"
REQ_PROMPT, GRADE_PROMPT = "code_requirements.md", "code_grade_system.md"
REQ_TOOL, GRADE_TOOL = "submit_requirements", "submit_code_grade"
VERDICTS = ("PASS", "FAIL", "UNSURE")
ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
NO_VERDICT = "no verdict from the model"
REQ_FIELDS = ("id", "requirement")

REQ_TOOL_DEF = {
    "name": REQ_TOOL,
    "description": "Submit the complete list of gradable requirements.",
    "input_schema": {
        "type": "object",
        "properties": {
            "requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "requirement": {"type": "string"},
                    },
                    "required": ["id", "requirement"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["requirements"],
        "additionalProperties": False,
    },
}

GRADE_TOOL_DEF = {
    "name": GRADE_TOOL,
    "description": "Submit one verdict per requirement.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "verdict": {"type": "string", "enum": list(VERDICTS)},
                        "reason": {"type": "string"},
                        "code_location": {"type": ["string", "null"]},
                    },
                    "required": ["id", "verdict", "reason", "code_location"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    },
}

# ----------------------------------------------------------------------- requirements


def check_requirements(raw: Any) -> list[str]:
    """Every problem with a requirement list, one sentence each (empty = valid)."""
    reqs = raw.get("requirements") if isinstance(raw, dict) else None
    if not isinstance(reqs, list) or not reqs:
        return ["requirements: must be a non-empty list of {id, requirement}."]
    errors: list[str] = []
    seen: set[str] = set()
    for n, r in enumerate(reqs, start=1):
        if not isinstance(r, dict) or not all(isinstance(r.get(k), str) for k in REQ_FIELDS):
            errors.append(f"requirement #{n}: needs the string fields id and requirement.")
            continue
        where = f"requirement #{n} ('{r['id']}')"
        if not ID_RE.match(r["id"]):
            errors.append(f"{where}: id must be snake_case (a-z, 0-9 and _, starting a-z).")
        elif r["id"] in seen:
            errors.append(f"{where}: id '{r['id']}' is already used by an earlier requirement.")
        seen.add(r["id"])
        if not r["requirement"].strip():
            errors.append(f"{where}: the requirement sentence is empty.")
    return errors


def _clean(reqs: list[dict]) -> list[dict]:
    """Only ``id`` and ``requirement`` (older saved lists may also carry a ``kind``)."""
    return [{k: r[k] for k in REQ_FIELDS} for r in reqs]


def make_requirements(
    client: LLMClient, handout_path: Path, cfg: LLMConfig, model: str
) -> tuple[dict, PlanResult]:
    """Ask for the requirement list (repair loop, at most 3 attempts). Raises LLMError."""
    system, version = load_prompt(REQ_PROMPT)
    handout = handout_path.read_text(encoding="utf-8").strip()
    user = f"Board: {BOARD}\n\n<handout>\n{handout}\n</handout>"
    req = LLMRequest(
        system, [{"role": "user", "content": user}], REQ_TOOL_DEF, model,
        cfg.code_grade_max_tokens, cfg.temperature,
    )  # fmt: skip
    result = repair_loop(client, req, check_requirements, what="requirements")
    tokens = result.tokens
    doc = {
        "handout": handout_path.as_posix(),
        "handout_sha256": file_sha256(handout_path),
        "board": BOARD,
        "model": model,
        "prompt_version": version,
        "attempts": result.attempts,
        "tokens": tokens,
        "latency_s": round(sum(r.latency_s for r in result.responses), 3),
        "cost_usd": cfg.cost_for(model, tokens["input"], tokens["output"]),
        "requirements": _clean(result.raw_plan["requirements"]) if result.ok else None,
        "errors": result.errors,
    }
    return doc, result


def write_requirements(doc: dict, result: PlanResult | None, out_dir: Path) -> Path:
    """``OUT/requirements.json``, plus the conversation log when the LLM made the list."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if result is not None:
        log = {"conversation": result.messages, "responses": [r.raw for r in result.responses]}
        _write_json(out_dir / "requirements.log.json", log)
    return _write_json(out_dir / "requirements.json", doc)


def load_requirements(path: Path) -> dict:
    """A saved ``requirements.json`` (or a bare list). Raises ValueError if invalid."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    doc = {"requirements": raw} if isinstance(raw, list) else raw
    errors = check_requirements(doc)
    if errors:
        raise ValueError(f"{path}: " + " ".join(errors))
    return {**doc, "requirements": _clean(doc["requirements"]), "reused_from": path.as_posix()}


# ---------------------------------------------------------------------------- grading


def grade_request(
    handout: str, reqs: list[dict], sub: Submission, cfg: LLMConfig, model: str, r: Redactor
) -> tuple[LLMRequest, list[str]]:
    """The grading request; this student's listed values are already ``<name>`` in it."""
    system, _ = load_prompt(GRADE_PROMPT)
    source, warnings = read_sources(sub.sketch_dir)
    source = r.hide(source).replace("</student_code>", "<\\/student_code>")
    values = "\n".join(f"- {k}: {r.hide(v)}" for k, v in sub.params.items()) or "none"
    user = (
        f"Board: {BOARD}\n\n<handout>\n{handout.strip()}\n</handout>\n\n"
        f"<requirements>\n{json.dumps(reqs, indent=2, ensure_ascii=False)}\n</requirements>\n\n"
        f"<student_values>\n{values}\n</student_values>\n\n"
        f'<student_code untrusted="true">\n{source}</student_code>'
    )
    msgs = [{"role": "user", "content": user}]
    return LLMRequest(
        system, msgs, GRADE_TOOL_DEF, model, cfg.code_grade_max_tokens, cfg.temperature
    ), warnings


def accept_grades(tool_input: Any, reqs: list[dict]) -> tuple[dict[str, dict], list[str]]:
    """Plain-code checks on the model's items, as ``feedback.accept_items`` does."""
    ids = {q["id"] for q in reqs}
    out: dict[str, dict] = {}
    warnings: list[str] = []
    items = tool_input.get("items") if isinstance(tool_input, dict) else None
    if not isinstance(items, list):
        return out, ["the code-grade tool input has no 'items' list"]
    for n, item in enumerate(items, start=1):
        rid = item.get("id") if isinstance(item, dict) else None
        if not isinstance(rid, str):
            warnings.append(f"item {n}: dropped, malformed (needs an id)")
        elif rid not in ids:
            warnings.append(f"item {n}: dropped, '{rid}' is not a requirement id")
        elif rid in out:
            warnings.append(f"item {n}: dropped, second item for '{rid}'")
        elif item.get("verdict") not in VERDICTS:
            warnings.append(f"item {n}: dropped, invalid verdict {item.get('verdict')!r}")
        else:
            reason, loc = item.get("reason"), item.get("code_location")
            out[rid] = {
                "verdict": item["verdict"],
                "reason": reason.strip() if isinstance(reason, str) else "",
                "code_location": loc.strip() if isinstance(loc, str) and loc.strip() else None,
            }
    return out, warnings


def _cut_off(raw: dict, tool_input: Any) -> str | None:
    """Why a reply can't be graded at all, or None: cut off at max_tokens, or no items."""
    if raw.get("stop_reason") == "max_tokens":
        return "the answer was cut off at max_tokens (raise max_tokens.code_grade)"
    if not (isinstance(tool_input, dict) and isinstance(tool_input.get("items"), list)):
        return f"the {GRADE_TOOL} tool input has no 'items' list"
    return None


def grade_submission(
    client: LLMClient, cfg: LLMConfig, model: str, handout: str, reqs: list[dict],
    sub: Submission,
) -> dict:  # fmt: skip
    """One grading call; returns the ``code_grade.json`` content. Never raises LLMError:
    a failed call makes every requirement ERROR."""
    r = Redactor(sub.params, cfg.redact_params)
    req, warnings = grade_request(handout, reqs, sub, cfg, model, r)
    _, version = load_prompt(GRADE_PROMPT)
    llm: dict[str, Any] = {"model": model, "prompt_version": version, "input_tokens": 0,
                           "output_tokens": 0, "latency_s": 0.0, "cost_usd": None,
                           "error": None}  # fmt: skip
    raw: dict[str, Any] = {
        "request": {"system": req.system, "messages": req.messages, "model": req.model}
    }
    resp = None
    try:
        resp = client.complete(req)
        if problem := _cut_off(resp.raw, resp.tool_input):
            raise LLMError(problem)  # tokens were still spent: resp stays set
    except LLMError as exc:
        llm["error"] = raw["error"] = str(exc)
        if isinstance(exc, NoToolCallError):
            resp = exc.response
        graded = {q["id"]: {"verdict": "ERROR", "reason": f"LLM error: {exc}",
                            "code_location": None} for q in reqs}  # fmt: skip
    else:
        graded, item_warnings = accept_grades(resp.tool_input, reqs)
        warnings += item_warnings
        missing = [q["id"] for q in reqs if q["id"] not in graded]
        for rid in missing:
            graded[rid] = {"verdict": "UNSURE", "reason": NO_VERDICT, "code_location": None}
        if missing:
            warnings.append(f"no verdict for: {', '.join(missing)} (counted as UNSURE)")
        for g in graded.values():  # the student reads real values; the saved raw stays redacted
            g["reason"] = r.show(g["reason"])
            g["code_location"] = g["code_location"] and r.show(g["code_location"])
    if resp is not None:
        raw["response"] = resp.raw
        llm.update(input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
                   latency_s=resp.latency_s, model=resp.model or model)  # fmt: skip
        llm["cost_usd"] = cfg.cost_for(model, resp.input_tokens, resp.output_tokens)
    return {
        "submission": sub.id,
        "board": BOARD,
        "params": sub.params,
        "requirements": [{**q, **graded[q["id"]]} for q in reqs],
        "llm": llm,
        "warnings": warnings,
        "raw": raw,
    }


# ------------------------------------------------------------------- outputs and metrics


@dataclass(frozen=True)
class CodeRow(BatchRow):
    """A batch row where ``borderline`` counts UNSURE."""

    llm_error: str | None = None


def code_row(result: dict, gt: GroundTruth | None, out: Path, elapsed_s: float) -> CodeRow:
    beh = [q["verdict"] for q in result["requirements"]]
    llm = result["llm"]
    return CodeRow(
        submission=result["submission"],
        faulty=gt.faulty if gt else None,
        fault=gt.fault if gt else None,
        passed=beh.count("PASS"),
        failed=beh.count("FAIL"),
        borderline=beh.count("UNSURE"),
        errors=beh.count("ERROR"),
        report_dir=out,
        llm_calls=1,
        input_tokens=llm["input_tokens"],
        output_tokens=llm["output_tokens"],
        llm_latency_s=llm["latency_s"],
        cost_usd=llm["cost_usd"],
        elapsed_s=elapsed_s,
        llm_error=llm["error"],
    )


def render_markdown(result: dict) -> str:
    rows = ["| Requirement | Verdict | Reason |", "|---|---|---|"]
    for q in result["requirements"]:
        why = q["reason"] + (f" ({q['code_location']})" if q["code_location"] else "")
        rows.append(f"| {md_escape(q['requirement'])} | {q['verdict']} | {md_escape(why)} |")

    llm = result["llm"]
    out = [
        f"# Code-only grade: {result['submission']}",
        "",
        f"> Baseline: {llm['model']} read the code only (no hardware, no measurement).",
        "",
    ]
    if llm["error"]:
        out += [f"**LLM error, nothing graded:** {md_escape(llm['error'])}", ""]
    out += [*rows, ""]
    return "\n".join(out)


def _write_json(path: Path, data: Any) -> Path:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


CSV_HEADER = [
    "submission", "ground_truth_faulty", "fault", "pass", "fail", "unsure", "flagged",
    "error", "llm_error", "llm_input_tokens", "llm_output_tokens",
    "llm_latency_s", "llm_cost_usd", "elapsed_s",
]  # fmt: skip


def write_summary_csv(rows: list[CodeRow], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(CSV_HEADER)
        for r in rows:
            w.writerow(
                [r.submission, "" if r.faulty is None else str(r.faulty).lower(), r.fault or "",
                 r.passed, r.failed, r.borderline, str(r.flagged).lower(), r.errors,
                 r.llm_error or "", r.input_tokens, r.output_tokens,
                 f"{r.llm_latency_s:.3f}", "" if r.cost_usd is None else f"{r.cost_usd:.6f}",
                 f"{r.elapsed_s:.1f}"]
            )  # fmt: skip


def run_code_grade(
    client: LLMClient,
    cfg: LLMConfig,
    model: str,
    handout: str,
    reqs: list[dict],
    submissions: list[Submission],
    labels: dict[str, GroundTruth],
    params: dict[str, dict[str, str]],
    out_dir: Path,
) -> tuple[list[CodeRow], BatchMetrics]:
    """Grade every submission (one call each); ``summary.csv`` is written even on Ctrl+C."""
    rows: list[CodeRow] = []
    try:
        for i, sub in enumerate(submissions, start=1):
            sub = replace(sub, params=params.get(sub.id, sub.params))
            tag = f"[{i}/{len(submissions)}] {sub.id}"
            print(f"{tag}: reading the code...", flush=True)
            t0 = time.monotonic()
            result = grade_submission(client, cfg, model, handout, reqs, sub)
            elapsed = time.monotonic() - t0
            folder = out_dir / sub.id
            folder.mkdir(parents=True, exist_ok=True)
            _write_json(folder / "code_grade.json", result)
            (folder / "code_grade.md").write_text(render_markdown(result), encoding="utf-8")
            row = code_row(result, labels.get(sub.id), folder, elapsed)
            rows.append(row)
            status = f"LLM error: {row.llm_error}" if row.llm_error else (
                f"{row.passed} PASS, {row.failed} FAIL, {row.borderline} UNSURE"
            )  # fmt: skip
            print(f"{tag}: {status} ({elapsed:.1f} s)", flush=True)
    finally:
        write_summary_csv(rows, out_dir / "summary.csv")
    return rows, compute_metrics(rows)


def format_table(rows: list[CodeRow], m: BatchMetrics, req_doc: dict) -> str:
    """Plain-ASCII table and totals, in the style of ``batch.format_table``."""
    head = f"{'submission':<28} {'truth':<16} {'PASS':>4} {'FAIL':>4} {'UNS':>4} {'ERR':>4}"
    lines = [head, "-" * len(head)]
    for r in rows:
        truth = "unlabelled" if r.faulty is None else r.fault or "faulty" if r.faulty else "correct"
        lines.append(
            f"{r.submission:<28} {truth:<16} {r.passed:>4} {r.failed:>4} {r.borderline:>4} "
            f"{r.errors:>4}"
        )
    lines += [
        "",
        f"Bug detection rate : {_pct(m.detection_rate)}  ({m.detected}/{m.faulty} faulty "
        "submissions with >= 1 FAIL)",
        f"False failure rate : {_pct(m.false_failure_rate)}  ({m.false_failures}/{m.correct} "
        "correct submissions with >= 1 FAIL)",
        f"UNSURE checks      : {m.borderline_checks}  (in {m.submissions_with_borderline} "
        "submission(s); counted as not failed)",
        f"ERROR checks       : {m.error_checks}  (in {m.submissions_with_error} submission(s))",
    ]
    if m.unlabelled:
        lines.append(f"Unlabelled         : {m.unlabelled} (no ground truth; excluded from rates)")
    reused = "reused_from" in req_doc
    tok = {"input": 0, "output": 0} if reused else req_doc.get("tokens") or {}
    req_calls = 0 if reused else req_doc.get("attempts", 0)
    what = "0 requirements, list reused" if reused else f"{req_calls} requirements"
    lines.append(
        f"LLM calls          : {m.llm_calls + req_calls} ({m.llm_calls} grading + {what}), "
        f"{m.input_tokens + tok.get('input', 0)} input + "
        f"{m.output_tokens + tok.get('output', 0)} output tokens"
    )
    req_cost = None if reused else req_doc.get("cost_usd")
    if m.cost_usd is None and req_cost is None:
        lines.append("LLM cost           : unknown (set price_per_mtok for this model)")
    else:
        total = (m.cost_usd or 0.0) + (req_cost or 0.0)
        per = (m.cost_usd or 0.0) / len(rows) if rows else 0.0
        lines.append(
            f"LLM cost           : ${total:.4f} total, ${per:.4f} per graded submission "
            f"(requirements: {'reused' if reused else f'${req_cost or 0.0:.4f}'}; list price)"
        )
    return "\n".join(lines)
