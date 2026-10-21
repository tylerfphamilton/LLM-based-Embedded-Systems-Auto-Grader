"""Plan generation with FakeLLMClient: repair loop, outputs, CLI. No network."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
import yaml
from typer.testing import CliRunner

from grader import cli
from grader.llm import FakeLLMClient, LLMConfig
from grader.planner import (
    PLAN_TOOL,
    file_sha256,
    first_request,
    generate_plan,
    plan_tool,
    write_outputs,
)

NOW = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)
CFG = LLMConfig(model="test-model")


@pytest.fixture
def good_plan(root) -> dict:
    return json.loads((root / "plans" / "pwm_1khz.json").read_text(encoding="utf-8"))


@pytest.fixture
def bad_plan(good_plan) -> dict:
    bad = json.loads(json.dumps(good_plan))
    bad["steps"][0]["pin"] = "D7"  # not in the pin map
    return bad


def _request(root):
    handout = (root / "handouts" / "pwm_1khz.md").read_text(encoding="utf-8")
    pinmap = (root / "config" / "pinmap.yaml").read_text(encoding="utf-8")
    return first_request("pwm_1khz", handout, pinmap, CFG)


def test_first_request_contents(root) -> None:
    req = _request(root)
    (msg,) = req.messages
    assert "<handout>" in msg["content"] and "1 kHz" in msg["content"]
    assert "D5:" in msg["content"]  # pin map YAML
    assert "freq_duty: frequency_hz, duty_pct, edge_count" in msg["content"]
    assert req.tool == plan_tool() and req.tool["name"] == PLAN_TOOL
    schema = req.tool["input_schema"]
    assert schema["type"] == "object" and "$schema" not in schema
    assert req.model == "test-model" and req.temperature is None


def test_valid_on_first_try(root, pinmap, good_plan) -> None:
    fake = FakeLLMClient([FakeLLMClient.tool_call(PLAN_TOOL, good_plan)])
    result = generate_plan(fake, _request(root), name="pwm_1khz", pinmap=pinmap)
    assert result.ok and result.attempts == 1 and result.raw_plan == good_plan
    assert len(fake.requests) == 1


def test_invalid_then_valid_sends_tool_result_error(root, pinmap, good_plan, bad_plan) -> None:
    fake = FakeLLMClient(
        [
            FakeLLMClient.tool_call(PLAN_TOOL, bad_plan, n=1),
            FakeLLMClient.tool_call(PLAN_TOOL, good_plan, n=2),
        ]
    )
    result = generate_plan(fake, _request(root), name="pwm_1khz", pinmap=pinmap)
    assert result.ok and result.attempts == 2
    second = fake.requests[1].messages
    assert [m["role"] for m in second] == ["user", "assistant", "user"]
    assert second[1]["content"][0]["id"] == "toolu_1"  # the model's own turn, unchanged
    (tr,) = second[2]["content"]
    assert tr["type"] == "tool_result" and tr["tool_use_id"] == "toolu_1" and tr["is_error"]
    assert tr["content"] == "step 'pwm': pin D7 is not in the pin map."


def test_wrong_assignment_name_is_an_error(root, pinmap, good_plan) -> None:
    fake = FakeLLMClient([FakeLLMClient.tool_call(PLAN_TOOL, good_plan)])
    result = generate_plan(fake, _request(root), name="other", pinmap=pinmap, max_attempts=1)
    assert not result.ok
    assert result.errors == ["assignment: must be 'other', not 'pwm_1khz'."]


def test_meta_file_contents(root, pinmap, good_plan, tmp_path) -> None:
    fake = FakeLLMClient(
        [
            FakeLLMClient.tool_call(PLAN_TOOL, {"nope": 1}),
            FakeLLMClient.tool_call(PLAN_TOOL, good_plan),
        ]
    )
    result = generate_plan(fake, _request(root), name="pwm_1khz", pinmap=pinmap)
    handout = root / "handouts" / "pwm_1khz.md"
    paths = write_outputs(result, name="pwm_1khz", handout_path=handout, out_dir=tmp_path, now=NOW)
    meta = yaml.safe_load(paths["meta"].read_text(encoding="utf-8"))
    assert paths["meta"] == tmp_path / "pwm_1khz.meta.yaml"
    assert meta["source"] == "llm" and meta["status"] == "draft"
    assert meta["handout_sha256"] == file_sha256(handout)
    assert meta["model"] == "fake-model" and len(meta["prompt_version"]) == 8
    assert meta["attempts"] == 2 and meta["tokens"] == {"input": 200, "output": 100}
    assert meta["generated_at"] == NOW.isoformat()
    assert meta["draft"] == (tmp_path / "drafts" / "pwm_1khz.draft.json").as_posix()
    assert meta["approved_by"] is None and meta["plan_sha256"] is None
    assert json.loads(paths["draft"].read_text(encoding="utf-8")) == good_plan
    log = json.loads(paths["log"].read_text(encoding="utf-8"))
    assert len(log["responses"]) == 2 and len(log["conversation"]) == 4


def _patch_client(monkeypatch, fake):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(cli.AnthropicClient, "from_config", classmethod(lambda cls, cfg: fake))


def _llm_config(tmp_path):
    path = tmp_path / "llm.yaml"
    path.write_text("model: test-model\n", encoding="utf-8")
    return str(path)


def test_cli_three_invalid_attempts_exit_nonzero(root, tmp_path, monkeypatch, bad_plan) -> None:
    fake = FakeLLMClient([FakeLLMClient.tool_call(PLAN_TOOL, bad_plan, n=i) for i in (1, 2, 3)])
    _patch_client(monkeypatch, fake)
    out = tmp_path / "plans"
    res = CliRunner().invoke(
        cli.app,
        ["make-plan", "--handout", str(root / "handouts/pwm_1khz.md"), "--name", "pwm_1khz",
         "--pinmap", str(root / "config/pinmap.yaml"), "--llm-config", _llm_config(tmp_path),
         "--out-dir", str(out)],
    )  # fmt: skip
    assert res.exit_code == 1, res.output
    assert "pin D7 is not in the pin map" in res.output
    assert len(fake.requests) == 3
    assert not (out / "drafts" / "pwm_1khz.draft.json").exists()
    assert not (out / "pwm_1khz.meta.yaml").exists() and not (out / "pwm_1khz.json").exists()
    assert (out / "drafts" / "pwm_1khz.log.json").exists()


def test_cli_success_writes_draft(root, tmp_path, monkeypatch, good_plan) -> None:
    _patch_client(monkeypatch, FakeLLMClient([FakeLLMClient.tool_call(PLAN_TOOL, good_plan)]))
    out = tmp_path / "plans"
    res = CliRunner().invoke(
        cli.app,
        ["make-plan", "--handout", str(root / "handouts/pwm_1khz.md"), "--name", "pwm_1khz",
         "--pinmap", str(root / "config/pinmap.yaml"), "--llm-config", _llm_config(tmp_path),
         "--out-dir", str(out)],
    )  # fmt: skip
    assert res.exit_code == 0, res.output
    assert (out / "drafts" / "pwm_1khz.draft.json").exists()
    assert not (out / "pwm_1khz.json").exists()  # a person copies the draft, not the tool


def test_dry_run_needs_no_key(root, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(cli.AnthropicClient, "complete", lambda *a: pytest.fail("API called"))
    res = CliRunner().invoke(
        cli.app,
        ["make-plan", "--handout", str(root / "handouts/pwm_1khz.md"), "--name", "pwm_1khz",
         "--pinmap", str(root / "config/pinmap.yaml"),
         "--llm-config", str(root / "config/llm.yaml"), "--dry-run"],
    )  # fmt: skip
    assert res.exit_code == 0, res.output
    assert "tool: submit_plan" in res.output and "valid JSON object schema" in res.output
    assert "estimated input tokens: ~" in res.output and "<handout>" in res.output


def test_cli_missing_key_is_a_clear_error(root, tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    res = CliRunner().invoke(
        cli.app,
        ["make-plan", "--handout", str(root / "handouts/pwm_1khz.md"), "--name", "pwm_1khz",
         "--pinmap", str(root / "config/pinmap.yaml"), "--llm-config", _llm_config(tmp_path),
         "--out-dir", str(tmp_path)],
    )  # fmt: skip
    assert res.exit_code == 2 and "ANTHROPIC_API_KEY is not set" in res.output
