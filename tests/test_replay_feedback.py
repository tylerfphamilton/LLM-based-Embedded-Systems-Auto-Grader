"""scripts/replay_feedback.py: new feedback on saved reports, verdicts untouched. No network."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

from grader.batch import grade_scenario
from grader.fake_rig import load_scenario
from grader.feedback import FEEDBACK_TOOL, LLMFeedback
from grader.llm import FakeLLMClient, LLMConfig
from grader.plan import load_plan
from grader.report import write_reports

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("replay", ROOT / "scripts" / "replay_feedback.py")
assert _spec and _spec.loader
replay_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(replay_mod)


def test_replay_adds_feedback_and_keeps_verdicts(tmp_path, pinmap, rig_profile) -> None:
    plan = load_plan(ROOT / "plans" / "pwm_1khz.json")
    reports = tmp_path / "reports"
    for name in ("wrong_pin", "correct"):  # correct has no FAIL, so no call
        scenario = load_scenario(ROOT / "scenarios" / "pwm" / f"{name}.yaml")
        r = grade_scenario(plan, scenario, pinmap=pinmap, rig_profile=rig_profile, repo_root=ROOT)
        write_reports(r, reports / name)  # a hardware batch names folders after sketches
    before = json.loads((reports / "wrong_pin" / "report.json").read_text(encoding="utf-8"))

    item = {"cited_value": None, "code_location": None}
    fake = FakeLLMClient(
        [
            FakeLLMClient.tool_call(
                FEEDBACK_TOOL,
                {
                    "items": [
                        {**item, "check_id": "pwm.frequency_hz", "explanation": "A or B.",
                         "cause_found": False, "same_cause_as": None},
                        {**item, "check_id": "pwm.duty_pct", "explanation": "No signal.",
                         "cause_found": False, "same_cause_as": "pwm.frequency_hz"},
                    ]
                },
            )
        ]
    )  # fmt: skip
    cfg = LLMConfig(model="test-model")
    paths = sorted(reports.glob("*/report.json"))
    out = tmp_path / "out"
    rows = replay_mod.replay(plan, paths, ROOT / "benchmark" / "pwm_1khz", out,
                             LLMFeedback(fake, cfg), cfg)  # fmt: skip

    assert len(fake.requests) == 1 and [r["id"] for r in rows] == ["wrong_pin"]
    assert "wrong_pin.ino" in fake.requests[0].messages[0]["content"]  # the real sketch
    after = json.loads((out / "wrong_pin" / "report.json").read_text(encoding="utf-8"))
    assert [c["verdict"] for c in after["checks"]] == [c["verdict"] for c in before["checks"]]
    assert [c["measured"] for c in after["checks"]] == [c["measured"] for c in before["checks"]]
    assert after["command_log"] == before["command_log"]
    by_id = {c["id"]: c for c in after["checks"]}
    assert by_id["pwm.duty_pct"]["same_cause_as"] == "pwm.frequency_hz"
    assert "**Possible causes:**" in (out / "wrong_pin" / "report.md").read_text("utf-8")
    with (out / "replay_summary.csv").open(encoding="utf-8") as f:
        (row,) = list(csv.DictReader(f))
    assert row["possible_causes"] == "2" and row["same_cause_as"] == "1"
    assert row["fault"] == "wrong_pin"
