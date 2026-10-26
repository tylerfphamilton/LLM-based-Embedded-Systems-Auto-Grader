# from __future__ import annotations

# from pathlib import Path
# from types import SimpleNamespace

# import pytest
# from pydantic import ValidationError

# from grader.clock import FakeClock
# from grader.fake_rig import FakeDevice, Scenario, load_scenario
# from grader.protocol import Err, Ok, parse_response
# from grader.transport import (
#     STLINK_VID,
#     FakeTransport,
#     SerialTransport,
#     TransportError,
#     TransportTimeout,
#     find_port,
# )

# ROOT = Path(__file__).resolve().parent.parent


# def make(**kw) -> FakeTransport:
#     return FakeTransport(FakeDevice(Scenario.model_validate({"submission": "t", **kw})))


# def ask(t: FakeTransport, line: str):
#     t.send_line(line)
#     return parse_response(t.read_line(1.0))


# def test_matching_by_cmd_and_pin() -> None:
#     t = make(
#         responses=[
#             {"match": {"cmd": "FREQ", "pin": "D5"}, "reply": {"frequency_hz": 1000.0}},
#             {"match": {"cmd": "FREQ"}, "reply": {"frequency_hz": 5.0}},
#         ]
#     )
#     assert ask(t, "FREQ D5 100") == Ok({"frequency_hz": 1000.0})
#     assert ask(t, "FREQ D13 100") == Ok({"frequency_hz": 5.0})


# def test_replies_are_consumed_in_order_then_exhausted() -> None:
#     t = make(
#         responses=[{"match": {"cmd": "DELAY"}, "replies": [{"delay_ms": 1.0}, {"delay_ms": 2.0}]}]
#     )
#     line = "DELAY D2 FALLING D13 ANY 50"
#     assert ask(t, line).fields == {"delay_ms": 1.0}
#     assert ask(t, line).fields == {"delay_ms": 2.0}
#     third = ask(t, line)
#     assert isinstance(third, Err) and "exhausted" in third.message


# def test_unmatched_measurement_gives_err_and_stimulus_gives_ok() -> None:
#     t = make()
#     assert ask(t, "ADC A0 16") == Err("BADCMD", "no scenario match")
#     assert ask(t, "DRIVE D2 BOUNCE 5 200 LOW") == Ok({})
#     assert ask(t, "UART 9600 SEND 4F4E") == Ok({})


# def test_bad_command_line_gives_badcmd() -> None:
#     resp = ask(make(), "FREQ D5")
#     assert isinstance(resp, Err) and resp.code == "BADCMD"


# def test_fail_command_error_and_silent() -> None:
#     t = make(
#         fail_command=[
#             {"cmd": "FREQ", "error": "ERR TIMEOUT no capture"},
#             {"cmd": "DRIVE", "match": {"pin": "D2"}, "silent": True},
#         ]
#     )
#     assert ask(t, "FREQ D5 100") == Err("TIMEOUT", "no capture")
#     t.send_line("DRIVE D2 HIGH")
#     with pytest.raises(TransportTimeout):
#         t.read_line(0.5)


# def test_seeded_noise_is_reproducible_and_bounded() -> None:
#     spec = {
#         "noise": {"seed": 42, "fields": {"frequency_hz": {"pct": 0.05}}},
#         "responses": [
#             {"match": {"cmd": "FREQ"}, "reply": {"frequency_hz": 1000.0, "edge_count": 100}}
#         ],
#     }

#     def run() -> list[float]:
#         t = make(**spec)
#         return [ask(t, "FREQ D5 100").fields["frequency_hz"] for _ in range(20)]

#     first = run()
#     assert first == run()
#     assert len(set(first)) > 1
#     assert all(abs(f - 1000.0) <= 0.5 for f in first)
#     assert ask(make(**spec), "FREQ D5 100").fields["edge_count"] == 100  # not noised


# def test_arm_collect_and_clock_advance() -> None:
#     clock = FakeClock()
#     scenario = Scenario.model_validate(
#         {"submission": "t", "responses": [{"match": {"cmd": "DELAY"}, "reply": {"delay_ms": 3.0}}]}
#     )
#     t = FakeTransport(FakeDevice(scenario, clock))
#     assert ask(t, "ARM DELAY D2 FALLING D13 ANY 50") == Ok({"slot": 0})
#     assert ask(t, "DRIVE D2 BOUNCE 5 200 LOW") == Ok({})
#     assert clock.monotonic() == pytest.approx(0.001)
#     assert ask(t, "COLLECT 0") == Ok({"delay_ms": 3.0})
#     assert clock.monotonic() == pytest.approx(0.051)
#     assert ask(t, "COLLECT 0").code == "NOSLOT"


# def test_debug_lines_are_emitted_before_reply() -> None:
#     t = make(debug_lines=True)
#     t.send_line("WAIT 1")
#     assert t.read_line(1).startswith("# ")
#     assert t.read_line(1) == "OK"


# @pytest.mark.parametrize(
#     "bad",
#     [
#         {"responses": [{"match": {"cmd": "FREQ"}}]},  # no reply
#         {"responses": [{"match": {"pin": "D5"}, "reply": {}}]},  # no cmd
#         {"fail_command": {"cmd": "FREQ", "error": "TIMEOUT"}},  # not an ERR line
#         {"default": {"error": "OK"}},
#         {"surprise": 1},
#     ],
# )
# def test_invalid_scenarios_rejected(bad: dict) -> None:
#     with pytest.raises(ValidationError):
#         Scenario.model_validate({"submission": "t", **bad})


# @pytest.mark.parametrize("path", sorted(ROOT.glob("scenarios/*/*.yaml")), ids=lambda p: p.stem)
# def test_example_scenarios_load(path: Path) -> None:
#     s = load_scenario(path)
#     assert s.ground_truth is not None and s.expected_verdicts


# # ------------------------------------------------------------------- serial (mocked)


# class FakeSerial:
#     def __init__(self, port: str, baudrate: int, timeout: float):
#         self.port, self.baudrate, self.timeout = port, baudrate, timeout
#         self.written = b""
#         self.incoming = [b"# booting\r\n", b"OK frequency_hz=1000.0\r\n", b"OK partial"]
#         self.closed = False

#     def write(self, data: bytes) -> None:
#         self.written += data

#     def flush(self) -> None:
#         pass

#     def readline(self) -> bytes:
#         return self.incoming.pop(0) if self.incoming else b""

#     def close(self) -> None:
#         self.closed = True


# def test_serial_transport_with_mocked_port() -> None:
#     ports = [
#         SimpleNamespace(device="COM3", vid=0x2341),
#         SimpleNamespace(device="COM7", vid=STLINK_VID),
#     ]
#     made: list[FakeSerial] = []

#     def factory(*a, **k) -> FakeSerial:
#         made.append(FakeSerial(*a, **k))
#         return made[-1]

#     t = SerialTransport(serial_factory=factory, port_lister=lambda: ports)
#     assert t.port == "COM7" and t.describe() == "serial:COM7"
#     t.send_line("FREQ D5 100")
#     assert made[0].written == b"FREQ D5 100\n"
#     assert t.read_line(2.0) == "# booting"
#     assert t.read_line(2.0) == "OK frequency_hz=1000.0"
#     assert made[0].timeout == 2.0
#     with pytest.raises(TransportTimeout):
#         t.read_line(0.1)  # no newline -> incomplete line
#     t.close()
#     assert made[0].closed


# def test_find_port_errors() -> None:
#     with pytest.raises(TransportError, match="no USB serial device"):
#         find_port(STLINK_VID, lister=lambda: [])
#     two = [SimpleNamespace(device=d, vid=STLINK_VID) for d in ("COM4", "COM5")]
#     with pytest.raises(TransportError, match="pass --port"):
#         find_port(STLINK_VID, lister=lambda: two)


from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from grader.clock import FakeClock
from grader.fake_rig import FakeDevice, Scenario, load_scenario
from grader.protocol import Err, Ok, parse_response
from grader.transport import (
    STLINK_VID,
    FakeTransport,
    SerialTransport,
    TransportError,
    TransportTimeout,
    find_port,
)

ROOT = Path(__file__).resolve().parent.parent


def make(**kw) -> FakeTransport:
    return FakeTransport(FakeDevice(Scenario.model_validate({"submission": "t", **kw})))


def ask(t: FakeTransport, line: str):
    t.send_line(line)
    return parse_response(t.read_line(1.0))


def test_matching_by_cmd_and_pin() -> None:
    t = make(
        responses=[
            {"match": {"cmd": "FREQ", "pin": "D5"}, "reply": {"frequency_hz": 1000.0}},
            {"match": {"cmd": "FREQ"}, "reply": {"frequency_hz": 5.0}},
        ]
    )
    assert ask(t, "FREQ D5 100") == Ok({"frequency_hz": 1000.0})
    assert ask(t, "FREQ D13 100") == Ok({"frequency_hz": 5.0})


def test_replies_are_consumed_in_order_then_exhausted() -> None:
    t = make(
        responses=[{"match": {"cmd": "DELAY"}, "replies": [{"delay_ms": 1.0}, {"delay_ms": 2.0}]}]
    )
    line = "DELAY D2 FALLING D13 ANY 50"
    assert ask(t, line).fields == {"delay_ms": 1.0}
    assert ask(t, line).fields == {"delay_ms": 2.0}
    third = ask(t, line)
    assert isinstance(third, Err) and "exhausted" in third.message


def test_unmatched_measurement_gives_err_and_stimulus_gives_ok() -> None:
    t = make()
    assert ask(t, "ADC A0 16") == Err("BADCMD", "no scenario match")
    assert ask(t, "DRIVE D2 BOUNCE 5 200 LOW") == Ok({})
    assert ask(t, "UART 9600 SEND 4F4E") == Ok({})


def test_bad_command_line_gives_badcmd() -> None:
    resp = ask(make(), "FREQ D5")
    assert isinstance(resp, Err) and resp.code == "BADCMD"


def test_fail_command_error_and_silent() -> None:
    t = make(
        fail_command=[
            {"cmd": "FREQ", "error": "ERR TIMEOUT no capture"},
            {"cmd": "DRIVE", "match": {"pin": "D2"}, "silent": True},
        ]
    )
    assert ask(t, "FREQ D5 100") == Err("TIMEOUT", "no capture")
    t.send_line("DRIVE D2 HIGH")
    with pytest.raises(TransportTimeout):
        t.read_line(0.5)


def test_seeded_noise_is_reproducible_and_bounded() -> None:
    spec = {
        "noise": {"seed": 42, "fields": {"frequency_hz": {"pct": 0.05}}},
        "responses": [
            {"match": {"cmd": "FREQ"}, "reply": {"frequency_hz": 1000.0, "edge_count": 100}}
        ],
    }

    def run() -> list[float]:
        t = make(**spec)
        return [ask(t, "FREQ D5 100").fields["frequency_hz"] for _ in range(20)]

    first = run()
    assert first == run()
    assert len(set(first)) > 1
    assert all(abs(f - 1000.0) <= 0.5 for f in first)
    assert ask(make(**spec), "FREQ D5 100").fields["edge_count"] == 100  # not noised


def test_arm_collect_and_clock_advance() -> None:
    clock = FakeClock()
    scenario = Scenario.model_validate(
        {"submission": "t", "responses": [{"match": {"cmd": "DELAY"}, "reply": {"delay_ms": 3.0}}]}
    )
    t = FakeTransport(FakeDevice(scenario, clock))
    assert ask(t, "ARM DELAY D2 FALLING D13 ANY 50") == Ok({"slot": 0})
    assert ask(t, "DRIVE D2 BOUNCE 5 200 LOW") == Ok({})
    assert clock.monotonic() == pytest.approx(0.001)
    assert ask(t, "COLLECT 0") == Ok({"delay_ms": 3.0})
    assert clock.monotonic() == pytest.approx(0.051)
    assert ask(t, "COLLECT 0").code == "NOSLOT"


def test_debug_lines_are_emitted_before_reply() -> None:
    t = make(debug_lines=True)
    t.send_line("WAIT 1")
    assert t.read_line(1).startswith("# ")
    assert t.read_line(1) == "OK"


@pytest.mark.parametrize(
    "bad",
    [
        {"responses": [{"match": {"cmd": "FREQ"}}]},  # no reply
        {"responses": [{"match": {"pin": "D5"}, "reply": {}}]},  # no cmd
        {"fail_command": {"cmd": "FREQ", "error": "TIMEOUT"}},  # not an ERR line
        {"default": {"error": "OK"}},
        {"surprise": 1},
    ],
)
def test_invalid_scenarios_rejected(bad: dict) -> None:
    with pytest.raises(ValidationError):
        Scenario.model_validate({"submission": "t", **bad})


@pytest.mark.parametrize("path", sorted(ROOT.glob("scenarios/*/*.yaml")), ids=lambda p: p.stem)
def test_example_scenarios_load(path: Path) -> None:
    s = load_scenario(path)
    assert s.ground_truth is not None and s.expected_verdicts


# ------------------------------------------------------------------- serial (mocked)


class FakeSerial:
    """Mimics pyserial. Like the ST-Link on Windows, changing `timeout` on the open port
    resets the link and drops whatever is in flight."""

    def __init__(self, port: str, baudrate: int, timeout: float):
        self.port, self.baudrate, self._timeout = port, baudrate, timeout
        self.timeout_changes = 0
        self.written = b""
        self.stale = b"garbage from before the port was opened\n"
        # Each chunk becomes readable on a later read() call, like bytes trickling in.
        self.chunks = [b"# boot", b"ing\r\n", b"OK frequency_hz=1000.0\r", b"\nOK partial"]
        self.flushed_input = False
        self.closed = False

    @property
    def timeout(self) -> float:
        return self._timeout

    @timeout.setter
    def timeout(self, value: float) -> None:
        self.timeout_changes += 1
        self.chunks.clear()  # the link reset loses everything in flight

    @property
    def in_waiting(self) -> int:
        return len(self.stale)

    def reset_input_buffer(self) -> None:
        self.stale = b""
        self.flushed_input = True

    def read(self, n: int) -> bytes:
        if self.stale:
            data, self.stale = self.stale[:n], self.stale[n:]
            return data
        return self.chunks.pop(0) if self.chunks else b""

    def write(self, data: bytes) -> None:
        self.written += data

    def flush(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def test_serial_transport_with_mocked_port() -> None:
    ports = [
        SimpleNamespace(device="COM3", vid=0x2341),
        SimpleNamespace(device="COM7", vid=STLINK_VID),
    ]
    made: list[FakeSerial] = []
    now = [0.0]

    def factory(*a, **k) -> FakeSerial:
        made.append(FakeSerial(*a, **k))
        return made[-1]

    def clock() -> float:
        now[0] += 0.05  # each poll costs one port timeout
        return now[0]

    t = SerialTransport(serial_factory=factory, port_lister=lambda: ports, monotonic=clock)
    assert t.port == "COM7" and t.describe() == "serial:COM7"
    assert made[0].flushed_input  # stale bytes from before open are discarded
    t.send_line("FREQ D5 100")
    assert made[0].written == b"FREQ D5 100\n"
    assert t.read_line(2.0) == "# booting"  # assembled from two chunks
    assert t.read_line(2.0) == "OK frequency_hz=1000.0"  # "\r" and "\n" in separate chunks
    with pytest.raises(TransportTimeout, match="OK partial"):
        t.read_line(0.5)  # no newline -> incomplete line, reported with what arrived
    assert made[0].timeout_changes == 0  # never touch the timeout of the open port
    t.close()
    assert made[0].closed


def test_find_port_errors() -> None:
    with pytest.raises(TransportError, match="no USB serial device"):
        find_port(STLINK_VID, lister=lambda: [])
    two = [SimpleNamespace(device=d, vid=STLINK_VID) for d in ("COM4", "COM5")]
    with pytest.raises(TransportError, match="pass --port"):
        find_port(STLINK_VID, lister=lambda: two)