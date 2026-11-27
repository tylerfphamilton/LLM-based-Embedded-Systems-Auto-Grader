"""Wiring guides (D69): pins per step, resistors, the rendered guide, TBD pins, the
committed guides and the CLI. No hardware, no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from grader import cli
from grader.llm import FakeLLMClient
from grader.pinmap import PinMap, load_pinmap, pinmap_hash
from grader.plan import load_plan, parse_plan
from grader.planner import PLAN_TOOL
from grader.wiring import WiringError, plan_connections, render_wiring, wiring_path

ROOT = Path(__file__).resolve().parent.parent
HAND_PLANS = ["blink_2hz", "pwm_1khz", "button_toggle", "uart_id"]
runner = CliRunner()


def _plan(*steps, reset=True):
    return parse_plan(
        {"schema_version": "0.1", "assignment": "t", "description": "d",
         "setup": {"reset": reset, "boot_wait_ms": 1000}, "steps": list(steps)}
    )  # fmt: skip


def _measure(id_, primitive, **kw):
    field = {"freq_duty": "edge_count", "logic_trace": "edge_count", "edge_delay": "delay_ms",
             "uart_read": "byte_count", "i2c_log": "read_count",
             "analog_read": "mean_mv"}  # fmt: skip
    return {"op": "measure", "id": id_, "requirement": "r", "primitive": primitive,
            "expect": [{"field": field[primitive], "op": "ge", "value": 0}], **kw}  # fmt: skip


def _pins(plan, pinmap) -> list[str]:
    return [c.nano for c in plan_connections(plan, pinmap)]


@pytest.fixture
def wired(pinmap) -> PinMap:
    """The real pin map with A0, A4 and A5 wired, so every primitive can be tested."""
    pins = {k: v.model_copy() for k, v in pinmap.pins.items()}
    for name, stm32 in (("A0", "PA4"), ("A4", "PB9"), ("A5", "PB8")):
        pins[name] = pins[name].model_copy(update={"stm32": stm32})
    return PinMap(pins=pins)


DELAY = {"from_pin": "D5", "from_edge": "rising", "to_pin": "D13", "to_edge": "any",
         "timeout_ms": 10}  # fmt: skip


@pytest.mark.parametrize(
    ("step", "expected"),
    [
        ({"op": "drive", "pin": "D2", "action": "high"}, ["D2"]),
        (_measure("f", "freq_duty", pin="D5", window_ms=10), ["D5"]),
        (_measure("t", "logic_trace", pin="D13", window_ms=10), ["D13"]),
        (_measure("a", "analog_read", pin="A0", samples=4), ["A0"]),
        (_measure("e", "edge_delay", **DELAY), ["D5", "D13"]),
        (_measure("u", "uart_read", baud=9600, window_ms=10), ["D0", "D1"]),  # pair
        ({"op": "uart_send", "baud": 9600, "data": "x"}, ["D0", "D1"]),
        ({"op": "dac_set", "pin": "A0", "mv": 100}, ["A0"]),
        ({"op": "i2c_emu", "addr": 104, "registers": {"0x3B": 1}}, ["A4", "A5"]),
        (_measure("i", "i2c_log", window_ms=10), ["A4", "A5"]),
        ({"op": "wait", "ms": 10}, []),
    ],
)
def test_each_step_adds_its_pins(step, expected, wired) -> None:
    assert _pins(_plan(step, reset=False), wired) == ["GND", *expected]


def test_gnd_first_and_rst_only_with_reset(pinmap) -> None:
    step = _measure("f", "freq_duty", pin="D5", window_ms=10)
    assert _pins(_plan(step), pinmap) == ["GND", "D5", "RST"]
    assert _pins(_plan(step, reset=False), pinmap) == ["GND", "D5"]
    rows = plan_connections(_plan(step), pinmap)
    assert rows[-1].direction == "rig drives" and rows[1].direction == "rig measures"


def test_a_pin_used_twice_is_one_row_with_each_use(pinmap) -> None:
    plan = load_plan(ROOT / "plans/button_toggle.json")
    rows = {c.nano: c for c in plan_connections(plan, pinmap)}
    assert list(rows) == ["GND", "D0", "D1", "D2", "D13", "RST"]  # digital by number, RST last
    assert rows["D2"].uses == (
        "button input (driven by the rig)", "delay start (edge watched)",
        "digital level (traced)",
    )  # fmt: skip
    assert rows["D2"].direction == "rig drives" and rows["D13"].direction == "rig measures"


def test_order_digital_then_analog_then_rst(wired) -> None:
    plan = _plan(
        _measure("a", "analog_read", pin="A0", samples=4),
        _measure("t", "logic_trace", pin="D13", window_ms=10),
        {"op": "drive", "pin": "D2", "action": "low"},
        _measure("f", "freq_duty", pin="D5", window_ms=10),
    )
    assert _pins(plan, wired) == ["GND", "D2", "D5", "D13", "A0", "RST"]


def test_button_toggle_resistors(pinmap) -> None:
    text = (ROOT / "plans/wiring_guides/button_toggle.wiring.md").read_text(encoding="utf-8")
    rows = {line.split(" | ")[1]: line for line in text.splitlines() if line.startswith("| ")}
    assert "1 kΩ in series" in rows["D2"] and "1 kΩ in series" in rows["D0"]
    assert "direct wire" in rows["D13"] and "direct wire" in rows["D1"]
    assert "| D7 | PA8 |" in rows["D2"]


def _guide(name, pinmap) -> str:
    plan = load_plan(ROOT / "plans" / f"{name}.json")
    return render_wiring(plan, pinmap, plan_connections(plan, pinmap), plan_file=f"{name}.json")


BUTTON_NOTE = "the student's `INPUT_PULLUP` holds it high. Don't add a pull-up resistor."
TX_RX = "TX goes to RX: Nano D1 (Serial1 TX) → the rig's receive pin (Nucleo D2, PA10)"


def test_plan_dependent_checklist_lines(pinmap) -> None:
    uart, button, pwm = (_guide(n, pinmap) for n in ("uart_id", "button_toggle", "pwm_1khz"))
    assert TX_RX in uart and BUTTON_NOTE not in uart
    assert BUTTON_NOTE in button
    assert TX_RX not in pwm and BUTTON_NOTE not in pwm
    assert pwm.startswith("# Wiring: pwm_1khz\n") and f"(hash `{pinmap_hash(pinmap)}`)" in pwm
    assert "checks the firmware, **not** the wires" in pwm and "Don't edit it by hand" in pwm


def test_tbd_pin_is_an_error(pinmap) -> None:
    plan = _plan(_measure("level", "analog_read", pin="A0", samples=4))
    with pytest.raises(WiringError, match=r"pin A0 is not wired yet .* step 'level' uses it"):
        plan_connections(plan, pinmap)


@pytest.mark.parametrize("name", HAND_PLANS)
def test_committed_guides_are_fresh_and_deterministic(name, pinmap) -> None:
    text = _guide(name, pinmap)
    assert text == _guide(name, pinmap) and "\r" not in text
    committed = wiring_path(ROOT / "plans" / f"{name}.json").read_text(encoding="utf-8")
    assert committed.replace("\r\n", "\n") == text, f"regenerate: grader wiring --plan {name}"


def test_pinmap_hash_unchanged_and_new_fields(pinmap) -> None:
    assert pinmap_hash(pinmap) == "46b391a6"  # the value before the wiring fields (D69)
    header = (ROOT / "firmware/src/pins_gen.h").read_text(encoding="utf-8")
    assert '#define PINMAP_HASH "46b391a6"' in header
    d2 = pinmap.pins["D2"]
    assert (d2.header, d2.series_ohms) == ("D7", 1000) and d2.note
    assert pinmap.pins["D13"].series_ohms is None and pinmap.pins["A0"].header is None
    with pytest.raises(ValidationError):
        PinMap.model_validate({"pins": {"D2": {"stm32": "PA8", "caps": [], "colour": "red"}}})


def test_cli_wiring_print_and_bad_plan(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(ROOT)  # the default --pinmap is config/pinmap.yaml
    res = runner.invoke(cli.app, ["wiring", "--plan", "plans/button_toggle.json", "--print"])
    assert res.exit_code == 0, res.output
    assert "| # | Nano 33 BLE pin | Nucleo pin (header) |" in res.output
    raw = json.loads((ROOT / "plans/pwm_1khz.json").read_text(encoding="utf-8"))
    raw["assignment"] = "tbd"
    raw["steps"] = [_measure("level", "analog_read", pin="A0", samples=4)]
    path = tmp_path / "tbd.json"
    path.write_text(json.dumps(raw), encoding="utf-8")
    res = runner.invoke(cli.app, ["wiring", "--plan", str(path), "--out", str(tmp_path / "w")])
    assert res.exit_code == 2 and "pin A0 is not wired yet" in res.output
    assert not (tmp_path / "w").exists()


def _make_plan(monkeypatch, tmp_path, plan: dict):
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake = FakeLLMClient([FakeLLMClient.tool_call(PLAN_TOOL, plan)])
    monkeypatch.setattr(cli.AnthropicClient, "from_config", classmethod(lambda cls, cfg: fake))
    (tmp_path / "llm.yaml").write_text("model: test-model\n", encoding="utf-8")
    return runner.invoke(
        cli.app,
        ["make-plan", "--handout", str(ROOT / "handouts/pwm_1khz.md"), "--name", "pwm_1khz",
         "--llm-config", str(tmp_path / "llm.yaml"), "--out-dir", str(tmp_path / "plans")],
    )  # fmt: skip


def test_make_plan_writes_the_wiring_guide(monkeypatch, tmp_path) -> None:
    plan = json.loads((ROOT / "plans/pwm_1khz.json").read_text(encoding="utf-8"))
    res = _make_plan(monkeypatch, tmp_path, plan)
    assert res.exit_code == 0, res.output
    guide = tmp_path / "plans" / "wiring_guides" / "pwm_1khz.wiring.md"
    assert guide.exists() and f"wiring: {guide}" in res.output
    assert "| D5 | A0 | PA0 |" in guide.read_text(encoding="utf-8")


def test_make_plan_with_a_tbd_pin_keeps_the_plan_and_exits_2(monkeypatch, tmp_path) -> None:
    plan = json.loads((ROOT / "plans/pwm_1khz.json").read_text(encoding="utf-8"))
    plan["steps"] = [_measure("level", "analog_read", pin="A0", samples=4)]
    res = _make_plan(monkeypatch, tmp_path, plan)
    assert res.exit_code == 2, res.output
    assert "can't be wired yet" in res.output and "pin A0 is not wired yet" in res.output
    assert (tmp_path / "plans" / "pwm_1khz.json").exists()
    assert not (tmp_path / "plans" / "wiring_guides" / "pwm_1khz.wiring.md").exists()


def test_real_pinmap_file_loads() -> None:
    assert load_pinmap(ROOT / "config/pinmap.yaml").pins["RST"].header == "A1"
