"""Live smoke tests against the real Anthropic API. They cost money.

Run only with:  ANTHROPIC_API_KEY=... pytest -m live
They also need a real model ID in config/llm.yaml (or GRADER_LIVE_CONFIG=<path>).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from grader.batch import grade_scenario
from grader.fake_rig import load_scenario
from grader.feedback import LLMFeedback
from grader.llm import MODEL_PLACEHOLDER, AnthropicClient, load_llm_config
from grader.plan import load_plan
from grader.planner import first_request, generate_plan

ROOT = Path(__file__).resolve().parent.parent
CFG = load_llm_config(os.environ.get("GRADER_LIVE_CONFIG", ROOT / "config" / "llm.yaml"))

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="ANTHROPIC_API_KEY unset"),
    pytest.mark.skipif(CFG.model == MODEL_PLACEHOLDER, reason="config/llm.yaml model unset"),
]


def test_live_make_plan(pinmap) -> None:
    req = first_request(
        "pwm_1khz",
        (ROOT / "handouts" / "pwm_1khz.md").read_text(encoding="utf-8"),
        (ROOT / "config" / "pinmap.yaml").read_text(encoding="utf-8"),
        CFG,
    )
    result = generate_plan(AnthropicClient.from_config(CFG), req, name="pwm_1khz", pinmap=pinmap)
    assert result.ok, result.errors  # also proves the API accepted the plan schema (D38)
    assert result.raw_plan["assumptions"]


def test_live_feedback(pinmap, rig_profile) -> None:
    scenario = load_scenario(ROOT / "scenarios" / "pwm" / "wrong_prescaler.yaml")
    plan = load_plan(ROOT / "plans" / "pwm_1khz.json")
    base = grade_scenario(plan, scenario, pinmap=pinmap, rig_profile=rig_profile, repo_root=ROOT)
    fb = LLMFeedback(AnthropicClient.from_config(CFG), CFG)
    r = grade_scenario(
        plan, scenario, pinmap=pinmap, rig_profile=rig_profile, feedback=fb, repo_root=ROOT
    )
    assert r.verdicts() == base.verdicts()
    assert r.llm is not None and r.llm.error is None, r.llm
    assert r.checks[0].feedback, r.llm.warnings
