"""Every example scenario must produce exactly the verdicts it declares.

This test is data-driven: a new assignment (plan + scenarios) is picked up automatically.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from grader.batch import grade_scenario
from grader.clock import FakeClock
from grader.compare import Verdict
from grader.fake_rig import FakeDevice, Scenario, load_scenario
from grader.flasher import ArduinoCliFlasher, Flasher, FlashResult, Submission
from grader.plan import PlanError, load_plan
from grader.report import render_markdown
from grader.runner import run
from grader.transport import ARDUINO_VID, FakeTransport

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = sorted(ROOT.glob("scenarios/*/*.yaml"))


def plan_for(scenario: Scenario):
    return load_plan(ROOT / "plans" / f"{scenario.assignment}.json")


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_scenario_verdicts(path: Path, pinmap, rig_profile) -> None:
    scenario = load_scenario(path)
    report = grade_scenario(plan_for(scenario), scenario, pinmap=pinmap, rig_profile=rig_profile)
    assert report.verdicts() == scenario.expected_verdicts
    # Rule 3: a rig fault never turns into a student FAIL.
    if any(v == "ERROR" for v in scenario.expected_verdicts.values()):
        assert report.rig_faults or all(
            c.reason.startswith("rig error") for c in report.checks if c.verdict == Verdict.ERROR
        )


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda p: f"{p.parent.name}/{p.stem}")
def test_determinism(path: Path, pinmap, rig_profile) -> None:
    scenario = load_scenario(path)
    plan = plan_for(scenario)

    def once() -> dict:
        r = grade_scenario(plan, scenario, pinmap=pinmap, rig_profile=rig_profile)
        d = json.loads(r.model_dump_json())
        d.pop("started_at"), d.pop("finished_at")
        return d

    assert once() == once()


def test_button_uses_arm_collect_on_the_wire(pinmap, rig_profile) -> None:
    scenario = load_scenario(ROOT / "scenarios/button/correct.yaml")
    report = grade_scenario(plan_for(scenario), scenario, pinmap=pinmap, rig_profile=rig_profile)
    tx = [e.line for e in report.command_log if e.dir == "tx"]
    assert tx[:7] == [
        "RESET",
        "WAIT 500",
        "DRIVE D2 RELEASE",
        "WAIT 100",
        "ARM DELAY D2 FALLING D13 ANY 100",
        "ARM UART 9600 READ 200",
        "DRIVE D2 BOUNCE 5 200 LOW",
    ]
    assert tx[7:9] == ["COLLECT 0", "COLLECT 1"]
    # Simulated time advances with the board-side waits/windows, so timestamps are meaningful.
    assert report.command_log[-1].t_ms > 1000


def test_debug_lines_are_logged_and_ignored(pinmap, rig_profile) -> None:
    scenario = load_scenario(ROOT / "scenarios/button/rig_stimulus_fault.yaml")
    report = grade_scenario(plan_for(scenario), scenario, pinmap=pinmap, rig_profile=rig_profile)
    assert any(e.dir == "debug" for e in report.command_log)
    assert len(report.rig_faults) == 2 and "ERR BUSY" in report.rig_faults[0]


def _pwm_run(pinmap, rig_profile, scenario: dict, flasher: Flasher | None = None):
    from grader.flasher import NoopFlasher

    clock = FakeClock()
    sc = Scenario.model_validate({"submission": "s", **scenario})
    return run(
        load_plan(ROOT / "plans/pwm_1khz.json"),
        Submission("s"),
        flasher or NoopFlasher(),
        FakeTransport(FakeDevice(sc, clock)),
        rig_profile,
        pinmap=pinmap,
        clock=clock,
    )


def test_silent_rig_is_error(pinmap, rig_profile) -> None:
    r = _pwm_run(pinmap, rig_profile, {"fail_command": {"cmd": "FREQ", "silent": True}})
    assert set(r.verdicts().values()) == {Verdict.ERROR}
    assert "no reply" in r.checks[0].reason


def test_malformed_reply_is_error(pinmap, rig_profile) -> None:
    r = _pwm_run(pinmap, rig_profile, {"responses": [{"match": {"cmd": "FREQ"}, "reply": {}}]})
    assert set(r.verdicts().values()) == {Verdict.ERROR}  # fields missing from the reply


def test_setup_failure_marks_everything_error(pinmap, rig_profile) -> None:
    r = _pwm_run(pinmap, rig_profile, {"fail_command": {"cmd": "RESET", "error": "ERR INTERNAL"}})
    assert set(r.verdicts().values()) == {Verdict.ERROR}
    assert [e.line for e in r.command_log if e.dir == "tx"] == ["RESET"]


class CompileFails(Flasher):
    kind = "test"

    def flash(self, submission: Submission) -> FlashResult:
        return FlashResult(False, "compile", "error: 'analogWrit' was not declared", True)


def test_compile_error_is_student_fail(pinmap, rig_profile) -> None:
    r = _pwm_run(pinmap, rig_profile, {}, CompileFails())
    assert set(r.verdicts().values()) == {Verdict.FAIL}
    assert r.command_log == []
    assert "did not compile" in render_markdown(r)


def test_invalid_plan_aborts(pinmap, rig_profile, tmp_path: Path) -> None:
    raw = json.loads((ROOT / "plans/pwm_1khz.json").read_text(encoding="utf-8"))
    raw["steps"][0]["pin"] = "D7"
    (tmp_path / "p.json").write_text(json.dumps(raw), encoding="utf-8")
    from grader.flasher import NoopFlasher

    with pytest.raises(PlanError, match="pin D7 is not in the pin map"):
        run(
            load_plan(tmp_path / "p.json"),
            Submission("s"),
            NoopFlasher(),
            FakeTransport(FakeDevice(Scenario(submission="s"))),
            rig_profile,
            pinmap=pinmap,
        )


def test_feedback_called_only_for_fail(pinmap, rig_profile) -> None:
    calls = []

    class Recorder:
        def explain(self, check, plan, submission):
            calls.append(check.id)
            return f"look at {check.field}"

    scenario = load_scenario(ROOT / "scenarios/pwm/wrong_prescaler.yaml")
    r = grade_scenario(
        plan_for(scenario), scenario, pinmap=pinmap, rig_profile=rig_profile, feedback=Recorder()
    )
    assert calls == ["pwm.frequency_hz"]
    assert "look at frequency_hz" in render_markdown(r)


def test_student_markdown(pinmap, rig_profile) -> None:
    scenario = load_scenario(ROOT / "scenarios/pwm/wrong_prescaler.yaml")
    md = render_markdown(
        grade_scenario(plan_for(scenario), scenario, pinmap=pinmap, rig_profile=rig_profile)
    )
    assert "**Result: 1 of 2 checks passed** · 1 failed" in md
    assert "| ≈ 1000 Hz ± 2% |" in md and "❌ FAIL" in md
    assert "## What to fix" in md and "Detailed feedback is not available yet" in md
    assert "## Not graded automatically" in md and "hardware timer" in md
    assert "FREQ D5" not in md  # no command log in the student report


# ------------------------------------------------------------------ arduino-cli (mocked)


def test_arduino_cli_flasher_success_and_failures(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    codes = {"compile": 0, "upload": 0}

    def fake_run(args, **kw):
        calls.append(args)
        return SimpleNamespace(returncode=codes[args[1]], stdout=f"{args[1]} ok\n", stderr="")

    ports = [SimpleNamespace(device="/dev/ttyACM1", vid=ARDUINO_VID)]
    fl = ArduinoCliFlasher(run=fake_run, port_lister=lambda: ports)
    sub = Submission("s", tmp_path)

    res = fl.flash(sub)
    assert res.ok and res.stage == "done"
    assert calls[0] == [
        "arduino-cli",
        "compile",
        "--fqbn",
        "arduino:mbed_nano:nano33ble",
        str(tmp_path),
    ]
    assert calls[1][:4] == ["arduino-cli", "upload", "-p", "/dev/ttyACM1"]

    codes["compile"] = 1
    res = fl.flash(sub)
    assert not res.ok and res.stage == "compile" and res.student_fault

    codes["compile"], codes["upload"] = 0, 1
    res = fl.flash(sub)
    assert not res.ok and res.stage == "upload" and not res.student_fault

    no_board = ArduinoCliFlasher(run=fake_run, port_lister=lambda: [])
    codes["upload"] = 0
    res = no_board.flash(sub)
    assert not res.ok and res.stage == "upload" and "no USB serial device" in res.log
