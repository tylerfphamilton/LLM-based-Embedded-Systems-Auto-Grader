"""Handout -> draft test plan through the LLM, with a validate-and-repair loop.

The LLM only drafts. A draft becomes a plan when a person copies it to
``plans/<name>.json`` and runs ``grader approve-plan``. Provenance lives in the sidecar
``plans/<name>.meta.yaml``.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from grader.llm import (
    LLMClient,
    LLMConfig,
    LLMRequest,
    LLMResponse,
    NoToolCallError,
    load_prompt,
    tool_use_block,
)
from grader.pinmap import PinMap
from grader.plan import PRIMITIVE_FIELDS, Plan, PlanError, export_schema, parse_plan
from grader.validate import validate_plan

PLAN_TOOL = "submit_plan"
PLAN_PROMPT = "plan_system.md"
MAX_ATTEMPTS = 3


def plan_tool() -> dict:
    """The ``submit_plan`` tool; its input schema is the exported plan JSON Schema."""
    schema = json.loads(export_schema())
    schema.pop("$schema", None)  # a meta-keyword, not part of the shape
    return {
        "name": PLAN_TOOL,
        "description": "Submit the complete test plan for the assignment.",
        "input_schema": schema,
    }


def user_message(name: str, handout: str, pinmap_yaml: str) -> str:
    prims = "\n".join(f"- {p}: {', '.join(fs)}" for p, fs in PRIMITIVE_FIELDS.items())
    return (
        f"Write the test plan for assignment `{name}`.\n\n"
        f"<handout>\n{handout.strip()}\n</handout>\n\n"
        f"<pin_map>\n{pinmap_yaml.strip()}\n</pin_map>\n\n"
        f"<primitives>\nEach measurement primitive and the result fields it returns:\n"
        f"{prims}\n</primitives>"
    )


def first_request(name: str, handout: str, pinmap_yaml: str, cfg: LLMConfig) -> LLMRequest:
    system, _ = load_prompt(PLAN_PROMPT)
    return LLMRequest(
        system=system,
        messages=[{"role": "user", "content": user_message(name, handout, pinmap_yaml)}],
        tool=plan_tool(),
        model=cfg.model,
        max_tokens=cfg.plan_max_tokens,
        temperature=cfg.temperature,
    )


def describe_request(req: LLMRequest, prompt_version: str = "") -> str:
    """Human-readable dump of a request for ``--dry-run`` (no API call)."""
    tool = req.tool or {}
    schema = tool.get("input_schema")
    schema_text = json.dumps(schema)
    ok = isinstance(schema, dict) and schema.get("type") == "object"
    user = "\n\n".join(m["content"] for m in req.messages if isinstance(m["content"], str))
    chars = len(req.system) + len(user) + len(schema_text)
    return "\n".join(
        [
            f"model: {req.model}   max_tokens: {req.max_tokens}   "
            f"temperature: {req.temperature}   prompt_version: {prompt_version or '?'}",
            f"tool: {tool.get('name')}   input_schema: {len(schema_text)} chars, "
            f"{'valid JSON object schema' if ok else 'NOT an object schema'}",
            f"estimated input tokens: ~{chars // 4} (characters / 4)",
            "",
            "===== system =====",
            req.system.rstrip(),
            "",
            "===== user =====",
            user,
        ]
    )


@dataclass
class PlanResult:
    ok: bool
    raw_plan: dict | None
    errors: list[str]
    attempts: int
    responses: list[LLMResponse] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)

    @property
    def tokens(self) -> dict[str, int]:
        return {
            "input": sum(r.input_tokens for r in self.responses),
            "output": sum(r.output_tokens for r in self.responses),
        }


def check_draft(raw: Any, name: str, pinmap: PinMap) -> list[str]:
    """Every problem with an LLM plan, as plain sentences (empty = valid)."""
    if not isinstance(raw, dict):
        return ["plan: the tool input is not a JSON object."]
    try:
        plan: Plan = parse_plan(raw)
    except PlanError as exc:
        return exc.errors
    errors = validate_plan(plan, pinmap)
    if plan.assignment != name:
        errors.append(f"assignment: must be '{name}', not '{plan.assignment}'.")
    return errors


def generate_plan(
    client: LLMClient,
    first: LLMRequest,
    *,
    name: str,
    pinmap: PinMap,
    max_attempts: int = MAX_ATTEMPTS,
) -> PlanResult:
    """Ask for a plan; on errors reply with an ``is_error`` tool_result and ask again.
    An answer without a ``submit_plan`` call is retried the same way (it uses an attempt).

    Raises ``LLMError`` if a call fails outright.
    """
    messages = list(first.messages)
    responses: list[LLMResponse] = []
    errors: list[str] = []
    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.complete(replace(first, messages=list(messages)))
        except NoToolCallError as exc:
            responses.append(exc.response)
            errors = [f"plan: no {PLAN_TOOL} call in the answer ({exc})."]
            if content := exc.response.raw.get("content"):
                messages.append({"role": "assistant", "content": content})
            messages.append(
                {"role": "user", "content": f"Call {PLAN_TOOL} with the complete plan."}
            )
            continue
        responses.append(resp)
        errors = check_draft(resp.tool_input, name, pinmap)
        messages.append({"role": "assistant", "content": resp.raw.get("content", [])})
        if not errors:
            return PlanResult(True, resp.tool_input, [], attempt, responses, messages)
        block = tool_use_block(resp.raw, PLAN_TOOL) or {}
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": block.get("id", ""),
                        "is_error": True,
                        "content": "\n".join(errors),
                    }
                ],
            }
        )
    return PlanResult(False, None, errors, max_attempts, responses, messages)


# --------------------------------------------------------------------------- provenance


def file_sha256(path: Path) -> str:
    """SHA-256 of the file bytes with CRLF normalised to LF (git autocrlf, see D40)."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def meta_path(plan_path: Path) -> Path:
    """``plans/<name>.json`` -> ``plans/<name>.meta.yaml``."""
    return plan_path.with_name(plan_path.stem + ".meta.yaml")


def load_meta(path: Path) -> dict | None:
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def write_meta(path: Path, meta: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True), encoding="utf-8")


def write_outputs(
    result: PlanResult,
    *,
    name: str,
    handout_path: Path,
    out_dir: Path,
    now: datetime,
) -> dict[str, Path]:
    """Always write the log; on success also the draft and the meta file."""
    drafts = out_dir / "drafts"
    drafts.mkdir(parents=True, exist_ok=True)
    _, prompt_version = load_prompt(PLAN_PROMPT)
    log = drafts / f"{name}.log.json"
    log.write_text(
        json.dumps(
            {
                "prompt_version": prompt_version,
                "ok": result.ok,
                "errors": result.errors,
                "conversation": result.messages,
                "responses": [r.raw for r in result.responses],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    paths = {"log": log}
    if not result.ok:
        return paths
    draft = drafts / f"{name}.draft.json"
    draft.write_text(json.dumps(result.raw_plan, indent=2, ensure_ascii=False) + "\n", "utf-8")
    meta = meta_path(out_dir / f"{name}.json")
    write_meta(
        meta,
        {
            "source": "llm",
            "status": "draft",
            "handout": handout_path.as_posix(),
            "handout_sha256": file_sha256(handout_path),
            "model": result.responses[-1].model,
            "prompt_version": prompt_version,
            "attempts": result.attempts,
            "tokens": result.tokens,
            "generated_at": now.isoformat(),
            "draft": draft.as_posix(),
            "approved_by": None,
            "approved_at": None,
            "plan_sha256": None,
        },
    )
    return {**paths, "draft": draft, "meta": meta}


def approve(plan_path: Path, by: str, now: datetime) -> dict:
    """Mark a reviewed plan approved; creates a ``source: hand`` meta file if there is none."""
    path = meta_path(plan_path)
    meta = load_meta(path) or {"source": "hand"}
    meta.update(
        status="approved",
        approved_by=by,
        approved_at=now.isoformat(),
        plan_sha256=file_sha256(plan_path),
    )
    write_meta(path, meta)
    return meta


def approval_warnings(plan_path: Path) -> list[str]:
    """Warnings for a plan whose meta file says it is not (or no longer) approved."""
    meta = load_meta(meta_path(plan_path))
    if meta is None:
        return []  # plans without provenance run normally
    name = plan_path.as_posix()
    if meta.get("status") != "approved":
        return [f"{name}: status is '{meta.get('status')}', not 'approved'; review it first."]
    if meta.get("plan_sha256") != file_sha256(plan_path):
        return [f"{name}: the file changed after it was approved; approve it again."]
    return []
