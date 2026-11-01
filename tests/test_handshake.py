"""PING handshake on connect and resync after a timeout (FakeRig, no hardware)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from grader.clock import FakeClock
from grader.compare import Verdict
from grader.fake_rig import FakeDevice, Scenario
from grader.flasher import Flasher, FlashResult, Submission
from grader.pinmap import pinmap_hash
from grader.plan import load_plan
from grader.protocol import PROTOCOL_VERSION
from grader.report import Report
from grader.runner import run
from grader.transport import FakeTransport

ROOT = Path(__file__).resolve().parent.parent


class RecordingFlasher(Flasher):
    kind = "test"

    def __init__(self) -> None:
        self.calls = 0

    def flash(self, submission: Submission) -> FlashResult:
        self.calls += 1
        return FlashResult(ok=True, stage="done")


def _button(pinmap, rig_profile, extra: dict[str, Any] | None = None, **device_kw):
    raw = yaml.safe_load((ROOT / "scenarios/button/correct.yaml").read_text(encoding="utf-8"))
    scenario = Scenario.model_validate({**raw, **(extra or {})})
    device_kw.setdefault("pinmap_hash", pinmap_hash(pinmap))
    clock = FakeClock()
    device = FakeDevice(scenario, clock, **device_kw)
    flasher = RecordingFlasher()
    report = run(
        load_plan(ROOT / "plans/button_toggle.json"),
        Submission("s"),
        flasher,
        FakeTransport(device),
        rig_profile,
        pinmap=pinmap,
        clock=clock,
    )
    return report, flasher, device


def _tx(report: Report) -> list[str]:
    return [e.line for e in report.command_log if e.dir == "tx"]


def _verdicts(report: Report) -> set[Verdict]:
    return set(report.verdicts().values())


def test_handshake_ok(pinmap, rig_profile) -> None:
    report, flasher, _ = _button(pinmap, rig_profile)
    assert _tx(report)[:2] == ["PING", "RESET"]
    assert flasher.calls == 1
    assert _verdicts(report) == {Verdict.PASS}
    assert report.rig_faults == [] and report.rig_warnings == []
    assert any(e.dir == "note" and e.line.startswith("handshake:") for e in report.command_log)


def test_protocol_mismatch_is_all_error_and_no_flash(pinmap, rig_profile) -> None:
    report, flasher, _ = _button(pinmap, rig_profile, {"ping": {"protocol": "0.1"}})
    assert flasher.calls == 0
    assert _tx(report) == ["PING"]
    assert _verdicts(report) == {Verdict.ERROR}
    assert f"protocol 0.1, the host speaks {PROTOCOL_VERSION}" in report.checks[0].reason
    assert report.rig_faults and "reflash" in report.rig_faults[0]


def test_pinmap_mismatch_is_all_error(pinmap, rig_profile) -> None:
    report, flasher, _ = _button(pinmap, rig_profile, pinmap_hash="a3f9c2e1")
    host = pinmap_hash(pinmap)
    assert flasher.calls == 0
    assert _verdicts(report) == {Verdict.ERROR}
    assert (
        f"firmware pin map a3f9c2e1 does not match the host's pin map {host}; reflash"
        in report.checks[0].reason
    )


def test_scenario_can_override_the_pinmap(pinmap, rig_profile) -> None:
    report, _, _ = _button(pinmap, rig_profile, {"ping": {"pinmap": "00000000"}})
    assert _verdicts(report) == {Verdict.ERROR}


def test_missing_pinmap_is_only_a_warning(pinmap, rig_profile) -> None:
    report, flasher, _ = _button(pinmap, rig_profile, {"ping": {"pinmap": None}})
    assert flasher.calls == 1
    assert _verdicts(report) == {Verdict.PASS}
    assert report.rig_faults == []
    assert len(report.rig_warnings) == 1 and "pin-map hash" in report.rig_warnings[0]


def test_ping_error_is_all_error(pinmap, rig_profile) -> None:
    report, flasher, _ = _button(pinmap, rig_profile, {"ping": {"error": "ERR INTERNAL boom"}})
    assert flasher.calls == 0 and _verdicts(report) == {Verdict.ERROR}


def test_silent_board_on_connect(pinmap, rig_profile) -> None:
    report, flasher, device = _button(pinmap, rig_profile, {"ping": {"silent": True}})
    assert flasher.calls == 0 and _verdicts(report) == {Verdict.ERROR}
    assert device.received == ["PING", "PING"]  # the request and one resync, then stop


class LoseFirstReply:
    """Wraps a device and drops its first reply, like bytes lost while the port opens."""

    def __init__(self, device: FakeDevice):
        self.device, self.calls = device, 0

    def handle(self, line: str) -> list[str]:
        self.calls += 1
        replies = self.device.handle(line)
        return [] if self.calls == 1 else replies


def test_lost_first_ping_reply_is_retried(pinmap, rig_profile) -> None:
    raw = yaml.safe_load((ROOT / "scenarios/button/correct.yaml").read_text(encoding="utf-8"))
    clock = FakeClock()
    device = FakeDevice(Scenario.model_validate(raw), clock, pinmap_hash=pinmap_hash(pinmap))
    report = run(
        load_plan(ROOT / "plans/button_toggle.json"),
        Submission("s"),
        RecordingFlasher(),
        FakeTransport(LoseFirstReply(device)),
        rig_profile,
        pinmap=pinmap,
        clock=clock,
    )
    assert device.received[:4] == ["PING", "PING", "PING", "RESET"]  # lost, resync, retry
    assert _verdicts(report) == {Verdict.PASS}
    assert report.rig_faults == ["resync after timeout on 'PING': the board answered PING"]


def test_timeout_then_successful_resync(pinmap, rig_profile) -> None:
    extra = {"fail_command": {"cmd": "COLLECT", "match": {"slot": 0}, "silent": True}}
    report, _, _ = _button(pinmap, rig_profile, extra)
    v = report.verdicts()
    assert {k for k, x in v.items() if x == Verdict.ERROR} == {
        "press1_led.delay_ms",
        "press1_led.to_edge_count",
    }
    assert all(x == Verdict.PASS for k, x in v.items() if not k.startswith("press1_led"))
    tx = _tx(report)
    assert tx[tx.index("COLLECT 0") + 1 : tx.index("COLLECT 0") + 3] == ["PING", "COLLECT 1"]
    assert report.rig_faults == ["resync after timeout on 'COLLECT 0': the board answered PING"]


def test_timeout_then_failed_resync_stops_sending(pinmap, rig_profile) -> None:
    extra = {
        "fail_command": [
            {"cmd": "COLLECT", "match": {"slot": 0}, "silent": True},
            {"cmd": "PING", "after": 1, "silent": True},  # answers the connect PING only
        ]
    }
    report, _, device = _button(pinmap, rig_profile, extra)
    assert _verdicts(report) == {Verdict.ERROR}
    assert device.received[-2:] == ["COLLECT 0", "PING"]  # nothing sent after the resync
    assert _tx(report)[-1] == "PING"
    assert "stopped responding" in report.rig_faults[-1]
    press2 = next(c for c in report.checks if c.id == "press2_led.delay_ms")
    assert press2.reason == "rig error: the measuring board stopped responding"


def test_fake_transport_drain_drops_pending_lines() -> None:
    t = FakeTransport(FakeDevice(Scenario(submission="s", debug_lines=True)))
    t.send_line("PING")  # a '#' line plus the reply
    t.drain()
    t.send_line("RESET")
    assert t.read_line(1.0).startswith("#") and t.read_line(1.0) == "OK"
