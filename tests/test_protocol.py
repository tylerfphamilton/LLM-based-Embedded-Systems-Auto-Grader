from __future__ import annotations

import pytest

from grader import protocol as pr
from grader.plan import load_plan
from grader.protocol import Debug, Err, Ok, ProtocolError, parse_command, parse_response

COMMANDS: list[tuple[pr.Command, str]] = [
    (pr.Reset(), "RESET"),
    (pr.Wait(500), "WAIT 500"),
    (pr.DriveLevel("D2", "high"), "DRIVE D2 HIGH"),
    (pr.DriveLevel("D2", "low"), "DRIVE D2 LOW"),
    (pr.DriveLevel("D2", "release"), "DRIVE D2 RELEASE"),
    (pr.DrivePulse("D2", 50, "low"), "DRIVE D2 PULSE 50 LOW"),
    (pr.DriveBounce("D2", 5, 200, "low"), "DRIVE D2 BOUNCE 5 200 LOW"),
    (pr.UartSend(9600, b"hi\n"), "UART 9600 SEND 68690A"),
    (pr.UartRead(9600, 500), "UART 9600 READ 500"),
    (pr.Dac("A0", 1650), "DAC A0 1650"),
    (pr.I2cEmu(0x68, ((0x3B, 0x10), (0x75, 0x68))), "I2C EMU 0x68 0x3B:0x10,0x75:0x68"),
    (pr.I2cEmu(0x68, ()), "I2C EMU 0x68"),
    (pr.I2cLog(250), "I2C LOG 250"),
    (pr.Freq("D5", 1000), "FREQ D5 1000"),
    (pr.Delay("D2", "falling", "D13", "any", 50), "DELAY D2 FALLING D13 ANY 50"),
    (pr.Trace("D13", 2000), "TRACE D13 2000"),
    (pr.Adc("A0", 64), "ADC A0 64"),
    (pr.Arm(pr.Freq("D5", 100)), "ARM FREQ D5 100"),
    (pr.Collect(3), "COLLECT 3"),
]


@pytest.mark.parametrize(("cmd", "line"), COMMANDS, ids=[line for _, line in COMMANDS])
def test_command_round_trip(cmd: pr.Command, line: str) -> None:
    assert cmd.to_line() == line
    assert parse_command(line) == cmd


def test_every_command_class_is_covered() -> None:
    covered = {type(c) for c, _ in COMMANDS}
    defined = {c for c in vars(pr).values() if isinstance(c, type) and issubclass(c, pr.Command)}
    assert defined - {pr.Command} == covered


@pytest.mark.parametrize(
    "line",
    [
        "",
        "JUMP D5",
        "FREQ D5",
        "FREQ D5 abc",
        "DRIVE D2 SIDEWAYS",
        "DRIVE D2 PULSE 5 MAYBE",
        "DELAY D2 UP D13 ANY 50",
        "UART 9600 SEND xyz",
        "ARM DRIVE D2 HIGH",
        "I2C EMU 0x68 0x75",
    ],
)
def test_malformed_commands_rejected(line: str) -> None:
    with pytest.raises(ProtocolError):
        parse_command(line)


def test_parse_ok_with_all_value_types() -> None:
    line = (
        'OK frequency_hz=999.8 edge_count=100 duty_pct=null edges_ms=[1.5,2,-3e-2] text="ON%0D%0A"'
    )
    assert parse_response(line) == Ok(
        {
            "frequency_hz": 999.8,
            "edge_count": 100,
            "duty_pct": None,
            "edges_ms": [1.5, 2, -0.03],
            "text": "ON\r\n",
        }
    )


def test_parse_empty_ok_and_list() -> None:
    assert parse_response("OK") == Ok({})
    assert parse_response("OK transactions=[]\r\n") == Ok({"transactions": []})


def test_parse_err_and_debug() -> None:
    assert parse_response("ERR TIMEOUT no edge on D13 within 50 ms") == Err(
        "TIMEOUT", "no edge on D13 within 50 ms"
    )
    assert parse_response("ERR BUSY") == Err("BUSY", "")
    assert parse_response("# capture armed on TIM2") == Debug("capture armed on TIM2")


@pytest.mark.parametrize(
    "text",
    ["ON", "hello world, again", 'quote " and % percent', "", "naïve ✓", "a=b c=d", "[x,y]"],
)
def test_string_round_trip(text: str) -> None:
    line = pr.format_response(Ok({"text": text, "list": [text, text]}))
    assert len(line.split(" ")) == 3  # OK + exactly one token per value
    assert parse_response(line) == Ok({"text": text, "list": [text, text]})


def test_invalid_utf8_is_replaced_not_fatal() -> None:
    assert parse_response('OK text="%FF%FEok"').fields["text"] == "��ok"


@pytest.mark.parametrize(
    "line",
    [
        "HELLO",
        "ok frequency_hz=1",
        "OK frequency_hz",
        "OK Frequency=1",
        "OK x=1 x=2",
        "OK x=abc",
        "OK x=nan",
        'OK x="unterminated',
        'OK x="bad%ZZ"',
        "OK x=[1,2",
        "ERR",
        "ERR lowercase message",
    ],
)
def test_malformed_responses_rejected(line: str) -> None:
    with pytest.raises(ProtocolError):
        parse_response(line)


def test_format_response_round_trip() -> None:
    for resp in [Ok({"a": 1, "b": -2.5, "c": None, "d": [], "e": ["x y"]}), Err("BADPIN", "D7?")]:
        assert parse_response(pr.format_response(resp)) == resp


def test_float_encoding_is_exact() -> None:
    for value in [0.1, 1000.0, 1e-7, 123456789.123, -0.0]:
        assert parse_response(pr.format_response(Ok({"v": value}))).fields["v"] == value


def test_command_for_every_step_in_example_plans(root) -> None:
    for plan_path in sorted((root / "plans").glob("*.json")):
        for step in load_plan(plan_path).steps:
            cmd = pr.command_for_step(step)
            assert parse_command(cmd.to_line()) == cmd


def test_pin_names_come_from_the_plan(root) -> None:
    plan = load_plan(root / "plans" / "button_toggle.json")
    lines = [pr.command_for_step(s).to_line() for s in plan.steps]
    assert "DELAY D2 FALLING D13 ANY 100" in lines
    assert "DRIVE D2 BOUNCE 5 200 LOW" in lines
