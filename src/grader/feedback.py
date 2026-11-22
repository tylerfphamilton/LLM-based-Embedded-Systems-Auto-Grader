"""Feedback for failed checks: one LLM call per submission.

Nothing here may influence a verdict. The runner calls ``explain_all`` only after every
verdict is final, and only if something FAILed; an LLM failure only means no feedback.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from grader.compare import Verdict
from grader.flasher import Submission
from grader.llm import LLMClient, LLMConfig, LLMError, LLMRequest, NoToolCallError, load_prompt
from grader.plan import Plan, is_measure
from grader.protocol import command_for_step
from grader.report import CheckResult, LLMInfo, LogEntry

FEEDBACK_TOOL = "submit_feedback"
FEEDBACK_PROMPT = "feedback_system.md"
SOURCE_SUFFIXES = (".ino", ".cpp", ".h")
SOURCE_LIMIT = 40_000  # characters of numbered source sent in total
MAX_PASSED = 10  # passed checks listed as context


@dataclass
class FeedbackResult:
    texts: dict[str, str] = field(default_factory=dict)  # check id -> explanation
    code_locations: dict[str, str] = field(default_factory=dict)
    llm: LLMInfo | None = None
    raw: dict | None = None  # request + raw response, saved as llm_feedback.json
    cause_found: dict[str, bool] = field(default_factory=dict)  # False = possible causes only
    same_cause_as: dict[str, str] = field(default_factory=dict)  # check id -> explained check id


class FeedbackGenerator(Protocol):
    def explain_all(
        self,
        checks: list[CheckResult],
        plan: Plan,
        submission: Submission,
        command_log: list[LogEntry],
    ) -> FeedbackResult:
        """Student-facing text for the FAIL checks (missing ids = no feedback)."""
        ...


class NullFeedback:
    """No feedback (no LLM, no network)."""

    def explain_all(self, checks, plan, submission, command_log) -> FeedbackResult:
        return FeedbackResult()


FEEDBACK_TOOL_DEF = {
    "name": FEEDBACK_TOOL,
    "description": "Submit one item per failed check; explain each root cause once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "check_id": {"type": "string"},
                        "explanation": {"type": "string"},
                        "cited_value": {"type": ["number", "string", "null"]},
                        "code_location": {"type": ["string", "null"]},
                        "cause_found": {"type": "boolean"},
                        "same_cause_as": {"type": ["string", "null"]},
                    },
                    "required": [
                        "check_id", "explanation", "cited_value", "code_location", "cause_found",
                        "same_cause_as",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"],
        "additionalProperties": False,
    },
}  # fmt: skip


def read_sources(sketch_dir: Path | None, limit: int = SOURCE_LIMIT) -> tuple[str, list[str]]:
    """Numbered ``*.ino/*.cpp/*.h`` files, capped at ``limit`` characters in total."""
    if sketch_dir is None or not sketch_dir.is_dir():
        return "(no source files available)", ["no sketch directory, so no source was sent"]
    files = sorted(p for p in sketch_dir.rglob("*") if p.suffix.lower() in SOURCE_SUFFIXES)
    parts: list[str] = []
    used = 0
    for path in files:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        body = "\n".join(f"{n:4}| {line}" for n, line in enumerate(lines, start=1))
        text = f"=== {path.relative_to(sketch_dir).as_posix()} ===\n{body}\n"
        if used + len(text) > limit:
            parts.append(text[: max(0, limit - used)] + "\n[... truncated: source limit ...]\n")
            return "".join(parts), [f"source truncated to {limit} characters"]
        parts.append(text)
        used += len(text)
    return ("".join(parts) or "(no source files found)"), [] if parts else ["no source files"]


def step_log(plan: Plan, step_ids: set[str], log: list[LogEntry]) -> list[str]:
    """Command-log lines (requests and replies) that belong to the given measure steps."""
    wanted = {
        command_for_step(s).to_line() for s in plan.steps if is_measure(s) and s.id in step_ids
    }
    out: list[str] = []
    slots: set[str] = set()
    keep = armed = False
    for e in log:
        if e.dir == "tx":
            line = e.line
            armed = line.startswith("ARM ") and line[4:] in wanted
            keep = line in wanted or armed or line in {f"COLLECT {s}" for s in slots}
        elif e.dir == "note":
            continue
        if keep:
            out.append(f"{e.dir} {e.line}")
            if armed and e.dir == "rx" and (m := re.search(r"\bslot=(\d+)", e.line)):
                slots.add(m.group(1))
    return out


def _flat(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else [value]


def _is_num(x: Any) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool)


_LEADING_NUMBER = re.compile(r"\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")
_ELLIPSIS = re.compile(r"(\.\.\.|\u2026).*\Z", re.S)  # "..." or an ellipsis character, and the rest
MIN_EXCERPT = 4  # characters an abbreviated text citation must keep


def same_value(cited: Any, actual: Any) -> bool:
    """Numbers equal to 3 significant figures; anything else must be equal. A cited
    string with a leading number ("500 Hz") counts as that number. A long text may be cited
    abbreviated: the part before a "..." must then appear in the actual text."""
    if isinstance(cited, str) and _is_num(actual) and (m := _LEADING_NUMBER.match(cited)):
        cited = float(m.group(1))
    if _is_num(cited) and _is_num(actual):
        return float(f"{cited:.3g}") == float(f"{actual:.3g}")
    if _is_num(cited) or _is_num(actual):
        return False
    if isinstance(cited, str) and isinstance(actual, str) and _ELLIPSIS.search(cited):
        excerpt = _ELLIPSIS.sub("", cited)
        return cited == actual or (len(excerpt) >= MIN_EXCERPT and excerpt in actual)
    return cited == actual


def accept_items(tool_input: Any, failed: list[CheckResult]) -> tuple[FeedbackResult, list[str]]:
    """Plain-code checks on the LLM's items. Returns (accepted feedback, warnings)."""
    by_id = {c.id: c for c in failed}
    fb = FeedbackResult()
    texts, locs = fb.texts, fb.code_locations
    refs: dict[str, str] = {}
    warnings: list[str] = []
    items = tool_input.get("items") if isinstance(tool_input, dict) else None
    if not isinstance(items, list):
        return fb, ["the feedback tool input has no 'items' list"]
    for n, item in enumerate(items, start=1):
        cid = item.get("check_id") if isinstance(item, dict) else None
        text = item.get("explanation") if isinstance(item, dict) else None
        if not isinstance(cid, str) or not isinstance(text, str) or not text.strip():
            warnings.append(f"item {n}: dropped, malformed (needs check_id and explanation)")
            continue
        check = by_id.get(cid)
        if check is None:
            warnings.append(f"item {n}: dropped, '{cid}' is not a failed check")
            continue
        if cid in texts:
            warnings.append(f"item {n}: dropped, second item for '{cid}'")
            continue
        cited = item.get("cited_value")
        if not any(same_value(cited, v) for v in _flat(check.measured) + _flat(check.expected)):
            warnings.append(
                f"item {n}: dropped, cited value {cited!r} for '{cid}' is neither the "
                f"measured ({check.measured!r}) nor the expected ({check.expected!r}) value"
            )
            continue
        texts[cid] = text.strip()
        loc = item.get("code_location")
        if isinstance(loc, str) and loc.strip():
            locs[cid] = loc.strip()
        if isinstance(found := item.get("cause_found"), bool):
            fb.cause_found[cid] = found
        if isinstance(ref := item.get("same_cause_as"), str) and ref.strip():
            refs[cid] = ref.strip()
    # A reference must point at another accepted item that has its own full explanation.
    for cid, ref in refs.items():
        if ref == cid or ref not in texts or ref in refs:
            warnings.append(
                f"'{cid}': same_cause_as '{ref}' ignored, it must name another failed check "
                "with its own explanation"
            )
            continue
        fb.same_cause_as[cid] = ref
        if ref in fb.cause_found:
            fb.cause_found[cid] = fb.cause_found[ref]
    missing = [c.id for c in failed if c.id not in texts]
    if missing:
        warnings.append(f"no accepted feedback for: {', '.join(missing)}")
    return fb, warnings


class Redactor:
    """Swaps listed per-student values (e.g. a student ID) for ``<name>`` and back (D63).

    A value is also hidden in its ``re.escape`` form, as it appears in ``matches`` checks.
    """

    def __init__(self, params: dict[str, str], names: tuple[str, ...]):
        self.tags = {f"<{n}>": params[n] for n in names if params.get(n)}
        pairs = {(form, tag) for tag, v in self.tags.items() for form in (v, re.escape(v))}
        self._pairs = sorted(pairs, key=lambda p: -len(p[0]))  # longest first

    def hide(self, text: str) -> str:
        for value, tag in self._pairs:
            text = text.replace(value, tag)
        return text

    def show(self, text: str) -> str:
        for tag, value in self.tags.items():
            text = text.replace(tag, value)
        return text

    def hide_any(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.hide(obj)
        if isinstance(obj, list):
            return [self.hide_any(x) for x in obj]
        return obj

    def hide_check(self, c: CheckResult) -> CheckResult:
        fields = ("requirement", "expected", "expected_text", "measured", "reason")
        return c.model_copy(update={f: self.hide_any(getattr(c, f)) for f in fields})


class LLMFeedback:
    """One ``submit_feedback`` call per submission that explains every FAIL check."""

    def __init__(self, client: LLMClient, cfg: LLMConfig):
        self.client, self.cfg = client, cfg

    def build_request(
        self,
        checks: list[CheckResult],
        plan: Plan,
        submission: Submission,
        command_log: list[LogEntry],
        redact: Callable[[str], str] = str,
    ) -> tuple[LLMRequest, list[str]]:
        """``redact`` is applied to the description, command log and source; ``checks``
        must already be redacted (``Redactor.hide_check``)."""
        failed = [c for c in checks if c.verdict == Verdict.FAIL]
        passed = [c for c in checks if c.verdict == Verdict.PASS][:MAX_PASSED]
        failed_json = json.dumps(
            [
                {
                    "check_id": c.id,
                    "requirement": c.requirement,
                    "expected": c.expected_text,
                    "expected_value": c.expected,
                    "measured": c.measured,
                    "reason": c.reason,
                }
                for c in failed
            ],
            indent=2,
            ensure_ascii=False,
        )
        step_ids = {c.step_id for c in failed if c.step_id}
        log = [redact(line) for line in step_log(plan, step_ids, command_log)]
        source, warnings = read_sources(submission.sketch_dir)
        source = redact(source).replace("</student_code>", "<\\/student_code>")
        passed_text = "\n".join(f"- {c.requirement} ({c.field})" for c in passed) or "(none)"
        user = (
            f"Assignment: {redact(plan.description)}\n\n"
            f"<passed_checks>\n{passed_text}\n</passed_checks>\n\n"
            f"<failed_checks>\n{failed_json}\n</failed_checks>\n\n"
            f"<command_log>\n{chr(10).join(log) or '(none)'}\n</command_log>\n\n"
            f'<student_code untrusted="true">\n{source}</student_code>'
        )
        system, _ = load_prompt(FEEDBACK_PROMPT)
        req = LLMRequest(
            system=system,
            messages=[{"role": "user", "content": user}],
            tool=FEEDBACK_TOOL_DEF,
            model=self.cfg.model,
            max_tokens=self.cfg.feedback_max_tokens,
            temperature=self.cfg.temperature,
        )
        return req, warnings

    def explain_all(
        self,
        checks: list[CheckResult],
        plan: Plan,
        submission: Submission,
        command_log: list[LogEntry],
    ) -> FeedbackResult:
        # The request and llm_feedback.json only ever see redacted values (D63).
        r = Redactor(submission.params, self.cfg.redact_params)
        checks = [r.hide_check(c) for c in checks]
        failed = [c for c in checks if c.verdict == Verdict.FAIL]
        _, version = load_prompt(FEEDBACK_PROMPT)
        req, warnings = self.build_request(checks, plan, submission, command_log, r.hide)
        info = LLMInfo(model=self.cfg.model, prompt_version=version, warnings=warnings)
        raw: dict[str, Any] = {
            "prompt_version": version,
            "request": {"system": req.system, "messages": req.messages, "model": req.model},
        }
        try:
            resp = self.client.complete(req)
        except LLMError as exc:
            info.error = str(exc)
            raw["error"] = str(exc)
            if isinstance(exc, NoToolCallError):  # e.g. max_tokens: the tokens were still paid
                r = exc.response
                info.input_tokens, info.output_tokens = r.input_tokens, r.output_tokens
                info.latency_s, raw["response"] = r.latency_s, r.raw
            return FeedbackResult(llm=info, raw=raw)
        fb, item_warnings = accept_items(resp.tool_input, failed)  # cited vs redacted values
        fb.texts = {k: r.show(v) for k, v in fb.texts.items()}
        fb.code_locations = {k: r.show(v) for k, v in fb.code_locations.items()}
        info.model = resp.model
        info.input_tokens, info.output_tokens = resp.input_tokens, resp.output_tokens
        info.latency_s = resp.latency_s
        info.warnings += item_warnings
        fb.llm, fb.raw = info, {**raw, "response": resp.raw}
        return fb
