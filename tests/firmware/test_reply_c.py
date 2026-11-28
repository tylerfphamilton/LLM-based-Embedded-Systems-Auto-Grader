"""Compile the plain-C firmware parts on the PC and check them against the host protocol.

reply.c, cmd.c and the generated pins_gen.h are built with the PC's C compiler together
with reply_harness.c. Every reply line must equal what grader.protocol.format_response()
produces for the same values: that is the proof that firmware and host agree.
Skipped if no C compiler (cc, gcc or clang) is on PATH.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path
from typing import Any, get_args

import pytest

from grader.pinmap import Capability, pinmap_hash
from grader.protocol import (
    PROTOCOL_VERSION,
    Dac,
    Err,
    Ok,
    UartRead,
    UartSend,
    format_response,
    parse_response,
)
from grader.validate import STANDARD_BAUDS

ROOT = Path(__file__).resolve().parents[2]
FW = ROOT / "firmware" / "src"
LINE_MAX = 1024

# harness rows "<kind>\t<pin>\t<reply>": one command run on every pin of the table
PER_PIN_CASES = ("freqpin", "tracepin", "drivepin", "delayfrom", "delayto", "dacpin")

COMPILER = next((c for c in ("cc", "gcc", "clang") if shutil.which(c)), None)
pytestmark = pytest.mark.skipif(
    COMPILER is None, reason="no C compiler (cc, gcc or clang) on PATH; firmware C not tested"
)


def fixed(scaled: int, decimals: int) -> float:
    return float(Decimal(scaled).scaleb(-decimals))


def ok(**fields: Any) -> str:
    return format_response(Ok(fields))


@pytest.fixture(scope="module")
def output(tmp_path_factory) -> tuple[dict[str, str], list[str]]:
    assert COMPILER is not None
    exe = tmp_path_factory.mktemp("fw") / "reply_harness.exe"
    sources = [
        Path(__file__).with_name("reply_harness.c"),
        FW / "reply.c",
        FW / "cmd.c",
        FW / "pins_table.c",
    ]
    cmd = [COMPILER, "-std=c11", "-Wall", "-Wextra", "-Werror", f"-I{FW}", "-o", str(exe)]
    build = subprocess.run([*cmd, *map(str, sources)], capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    run = subprocess.run([str(exe)], capture_output=True, text=True, check=True)
    cases: dict[str, str] = {}
    pins: list[str] = []
    for row in run.stdout.splitlines():
        name, _, line = row.partition("\t")
        if name == "pin":
            pins.append(line)
        else:
            if name in PER_PIN_CASES:  # "<kind>\t<pin>\t<reply>" -> "<kind>:<pin>"
                pin, _, line = line.partition("\t")
                name = f"{name}:{pin}"
            assert name not in cases, name
            cases[name] = line
    return cases, pins


def test_ints(output) -> None:
    assert output[0]["ints"] == ok(a=0, b=1000, c=-42, d=2**63 - 1, e=-(2**63))


def test_fixed_point(output) -> None:
    assert output[0]["fixed"] == ok(
        f=fixed(999873, 3),
        zero=fixed(0, 3),
        neg=fixed(-1500, 3),
        negsmall=fixed(-5, 3),
        whole=fixed(1000000, 3),
        nodec=fixed(7, 0),
        pct=fixed(4998, 2),
    )
    assert output[0]["fixed"].startswith("OK f=999.873 zero=0.0 neg=-1.5 negsmall=-0.005")


def test_null(output) -> None:
    assert output[0]["null"] == ok(frequency_hz=None, edge_count=1)


def test_strings(output) -> None:
    assert output[0]["strings"] == ok(
        empty=b"",
        plain=b"ON",
        space=b"hello world",
        punct=b'a,b"c%d',
        ctrl=b"ON\r\n\t\x01\x7f",
        nul=b"a\x00b",
        utf8="café µs".encode(),
        high=b"\xff\x80",
    )
    assert parse_response(output[0]["strings"]).fields["utf8"] == "café µs"  # type: ignore[union-attr]


def test_lists(output) -> None:
    assert output[0]["empty_list"] == ok(edges_ms=[])
    values = [fixed(v, 3) for v in (500, 250500, -1, 0, 1000)]
    assert output[0]["list"] == ok(edge_count=5, edges_ms=values, final_level=1)


def test_truncated_list_stops_before_the_line_limit(output) -> None:
    line = output[0]["truncated_list"]
    values = [fixed(123456 + 1000 * i, 3) for i in range(400)]
    kept = len(parse_response(line).fields["edges_ms"])  # type: ignore[union-attr]
    assert 0 < kept < len(values)
    assert line == ok(edge_count=400, edges_ms=values[:kept], truncated=1)
    assert len(line) <= LINE_MAX
    one_more = ok(edge_count=400, edges_ms=values[: kept + 1], truncated=1)
    assert len(one_more) > LINE_MAX  # it kept as many as fit


def test_overflow_becomes_internal_error(output) -> None:
    assert output[0]["overflow"] == format_response(Err("INTERNAL", "reply too long"))


def test_err_lines(output) -> None:
    assert output[0]["err"] == format_response(Err("BADPIN", "pin D7 is not in the pin map"))
    assert output[0]["err_nomsg"] == format_response(Err("TIMEOUT"))
    assert output[0]["ping_args"] == "ERR BADCMD PING takes 0 arguments, got 1"
    assert output[0]["unknown"] == "ERR BADCMD unknown verb JUMP"
    assert output[0]["blank"] == "ERR BADCMD empty request"


def test_ping_reports_versions_and_pinmap_hash(output, pinmap) -> None:
    version_h = (FW / "version.h").read_text(encoding="utf-8")
    fw = re.search(r'#define FW_VERSION "([^"]+)"', version_h)
    proto = re.search(r'#define PROTOCOL_VERSION "([^"]+)"', version_h)
    assert fw and proto
    assert proto.group(1) == PROTOCOL_VERSION, "firmware/src/version.h and protocol.py disagree"
    expected = ok(fw=fw.group(1), protocol=PROTOCOL_VERSION, pinmap=pinmap_hash(pinmap))
    assert output[0]["ping"] == expected


def test_generated_pin_table_matches_pinmap(output, pinmap) -> None:
    caps = get_args(Capability)
    expected = []
    for name, info in sorted(pinmap.pins.items()):
        m = re.fullmatch(r"P([A-K])(\d{1,2})", info.stm32)
        port, num = (m.group(1), int(m.group(2))) if m else ("-", 0)
        bits = sum(1 << n for n, c in enumerate(caps) if c in info.caps)
        expected.append(f"{name} {port} {num} {bits}")
    assert output[1] == expected


# --------------------------------------------------------------------------- FREQ


def _wired(stm32: str) -> re.Match[str] | None:
    return re.fullmatch(r"P([A-K])(\d{1,2})", stm32)


def test_freq_checks_every_pin_against_the_pin_map(output, pinmap) -> None:
    """FREQ runs only on wired timer_capture pins; every other pin is a BADPIN rig fault."""
    one_khz = ok(frequency_hz=1000.0, duty_pct=25.0, edge_count=100)
    for name, info in pinmap.pins.items():
        line = output[0][f"freqpin:{name}"]
        if "timer_capture" not in info.caps:
            want = Err("BADPIN", f"pin {name} has no timer_capture capability")
            assert line == format_response(want), name
        elif not _wired(info.stm32):
            want = Err("BADPIN", f"pin {name} is not wired (TBD in the pin map)")
            assert line == format_response(want), name
        else:
            assert line == one_khz, name
    unknown = Err("BADPIN", "pin D99 is not in the pin map")
    assert output[0]["freq_unknown"] == format_response(unknown)


@pytest.fixture
def freq_cases(output, pinmap) -> dict[str, str]:
    cases = output[0]
    if "freq_pin" not in cases:
        pytest.skip("no wired timer_capture pin in config/pinmap.yaml")
    m = _wired(pinmap.pins[cases["freq_pin"]].stm32)
    assert m
    cases = dict(cases)
    cases["_stm32"] = f"{m.group(1)} {int(m.group(2))}"
    return cases


def test_freq_measures_through_the_mapped_stm32_pin(freq_cases) -> None:
    assert freq_cases["freq_call"] == f"{freq_cases['_stm32']} 100"


def test_freq_arithmetic(freq_cases) -> None:
    assert freq_cases["freq_1k"] == ok(frequency_hz=1000.0, duty_pct=25.0, edge_count=100)
    assert freq_cases["freq_500"] == ok(frequency_hz=500.0, duty_pct=25.1, edge_count=50)
    # 80 MHz / 78447 ticks = 1019.7968 Hz; 19612 / 78447 = 25.0003 %
    assert freq_cases["freq_odd"] == ok(frequency_hz=1019.797, duty_pct=25.0, edge_count=102)


def test_freq_no_signal_is_a_valid_measurement(freq_cases) -> None:
    assert freq_cases["freq_nosig"] == ok(frequency_hz=None, duty_pct=None, edge_count=0)
    assert freq_cases["freq_one"] == ok(frequency_hz=None, duty_pct=None, edge_count=1)


def test_freq_rig_problems_are_errors(freq_cases) -> None:
    pin = freq_cases["freq_pin"]
    port, num = freq_cases["_stm32"].split()
    overrun = Err("INTERNAL", "capture overrun: signal too fast to time every edge")
    assert freq_cases["freq_overrun"] == format_response(overrun)
    notimer = Err("BADPIN", f"no capture timer on P{port}{num} (pin {pin})")
    assert freq_cases["freq_notimer"] == format_response(notimer)
    assert freq_cases["freq_hw"] == format_response(Err("INTERNAL", "capture timer setup failed"))


def test_freq_argument_checks(freq_cases) -> None:
    bad_window = format_response(Err("BADARG", "window_ms must be 1-10000"))
    for case in ("freq_win0", "freq_winbig", "freq_winsyntax"):
        assert freq_cases[case] == bad_window, case
    assert freq_cases["freq_winmax"].startswith("OK ")
    assert freq_cases["freq_args"] == "ERR BADCMD FREQ takes 2 arguments, got 1"


# --------------------------------------------------------------------------- WAIT


def test_wait_sleeps_then_replies_ok(output) -> None:
    cases = output[0]
    for case, ms in (("wait_500", 500), ("wait_0", 0), ("wait_max", 60000)):
        assert cases[case] == ok(), case
        assert cases[f"{case}_slept"] == str(ms), case


def test_wait_rejects_bad_arguments_without_sleeping(output) -> None:
    cases = output[0]
    bad = format_response(Err("BADARG", "ms must be 0-60000"))
    for case in ("wait_big", "wait_neg", "wait_frac"):
        assert cases[case] == bad, case
    assert cases["wait_args"] == "ERR BADCMD WAIT takes 1 arguments, got 0"
    assert cases["wait_extra"] == "ERR BADCMD WAIT takes 1 arguments, got 2"
    for case in ("wait_big", "wait_neg", "wait_frac", "wait_args", "wait_extra"):
        assert cases[f"{case}_slept"] == "-1", case  # never slept


# --------------------------------------------------------------------------- RESET


def _reset_row(pinmap):
    rows = [(name, info) for name, info in pinmap.pins.items() if "reset" in info.caps]
    assert len(rows) <= 1, "more than one reset line in the pin map"
    return rows[0] if rows else (None, None)


def test_reset_pulses_the_mapped_line_once(output, pinmap) -> None:
    cases = output[0]
    name, info = _reset_row(pinmap)
    m = _wired(info.stm32) if info else None
    if name is None:
        assert cases["reset_ok"] == format_response(Err("BADPIN", "no reset line in the pin map"))
        assert cases["reset_ok_pulse"].startswith("0 ")
    elif m is None:
        want = Err("BADPIN", f"reset line {name} is not wired (TBD in the pin map)")
        assert cases["reset_ok"] == format_response(want)
        assert cases["reset_ok_pulse"].startswith("0 ")
    else:
        assert cases["reset_ok"] == ok()
        assert cases["reset_ok_pulse"] == f"1 {m.group(1)} {int(m.group(2))}"  # exactly one


def test_reset_errors(output, pinmap) -> None:
    cases = output[0]
    _, info = _reset_row(pinmap)
    m = _wired(info.stm32) if info else None
    if m is not None:
        want = Err("INTERNAL", f"could not drive reset line P{m.group(1)}{int(m.group(2))}")
        assert cases["reset_hw"] == format_response(want)
    assert cases["reset_args"] == "ERR BADCMD RESET takes 0 arguments, got 1"
    assert cases["reset_args_pulse"] == "0"  # a rejected RESET must not touch the line


# --------------------------------------------------------------------------- TRACE


def test_trace_checks_every_pin_against_the_pin_map(output, pinmap) -> None:
    """TRACE runs only on wired gpio pins; every other pin is a BADPIN rig fault."""
    blink = ok(
        edge_count=8,
        final_level=1,
        edges_ms=[100.0 + 250.0 * i for i in range(8)],
    )
    for name, info in pinmap.pins.items():
        line = output[0][f"tracepin:{name}"]
        if "gpio" not in info.caps:
            want = Err("BADPIN", f"pin {name} has no gpio capability")
            assert line == format_response(want), name
        elif not _wired(info.stm32):
            want = Err("BADPIN", f"pin {name} is not wired (TBD in the pin map)")
            assert line == format_response(want), name
        else:
            assert line == blink, name
    unknown = Err("BADPIN", "pin D99 is not in the pin map")
    assert output[0]["trace_unknown"] == format_response(unknown)


@pytest.fixture
def trace_cases(output, pinmap) -> dict[str, str]:
    cases = output[0]
    if "trace_pin" not in cases:
        pytest.skip("no wired gpio pin in config/pinmap.yaml")
    m = _wired(pinmap.pins[cases["trace_pin"]].stm32)
    assert m
    cases = dict(cases)
    cases["_stm32"] = f"{m.group(1)} {int(m.group(2))}"
    return cases


def test_trace_measures_through_the_mapped_stm32_pin(trace_cases) -> None:
    assert trace_cases["trace_call"] == f"{trace_cases['_stm32']} 2000"


def test_trace_edges_and_levels(trace_cases) -> None:
    blink = [100.0 + 250.0 * i for i in range(8)]
    assert trace_cases["trace_blink"] == ok(edge_count=8, final_level=1, edges_ms=blink)
    assert trace_cases["trace_low"] == ok(edge_count=0, final_level=0, edges_ms=[])
    assert trace_cases["trace_high"] == ok(edge_count=0, final_level=1, edges_ms=[])
    # microsecond resolution, measured from the window start across the counter wrap
    fine = [0.001, 1234.568, 2469.135]
    assert trace_cases["trace_fine"] == ok(edge_count=3, final_level=0, edges_ms=fine)


def test_trace_long_lists_are_truncated_but_counted(trace_cases) -> None:
    line = trace_cases["trace_long"]
    edges = parse_response(line).fields["edges_ms"]  # type: ignore[union-attr]
    kept = len(edges)
    assert 0 < kept < 300
    want = [float(i + 1) for i in range(kept)]
    assert line == ok(edge_count=300, final_level=0, edges_ms=want, truncated=1)
    assert len(line) <= LINE_MAX
    # the firmware's buffer filled (40 of 50 stored) but the list fits: still truncated=1
    stored = [float(i + 1) for i in range(40)]
    want_full = ok(edge_count=50, final_level=0, edges_ms=stored, truncated=1)
    assert trace_cases["trace_bufull"] == want_full


def test_trace_errors(trace_cases) -> None:
    pin = trace_cases["trace_pin"]
    port, num = trace_cases["_stm32"].split()
    noport = Err("INTERNAL", f"no GPIO port {port} (pin {pin})")
    assert trace_cases["trace_noport"] == format_response(noport)
    hw = Err("INTERNAL", f"edge capture setup failed on P{port}{num}")
    assert trace_cases["trace_hw"] == format_response(hw)
    bad_window = format_response(Err("BADARG", "window_ms must be 1-10000"))
    assert trace_cases["trace_win0"] == bad_window
    assert trace_cases["trace_winbig"] == bad_window
    assert trace_cases["trace_args"] == "ERR BADCMD TRACE takes 2 arguments, got 1"


# --------------------------------------------------------------------------- DRIVE


def test_drive_checks_every_pin_against_the_pin_map(output, pinmap) -> None:
    """DRIVE runs only on wired pins with the drive capability (never RST, never inputs)."""
    for name, info in pinmap.pins.items():
        line = output[0][f"drivepin:{name}"]
        if "drive" not in info.caps:
            want = Err("BADPIN", f"pin {name} has no drive capability")
            assert line == format_response(want), name
        elif not _wired(info.stm32):
            want = Err("BADPIN", f"pin {name} is not wired (TBD in the pin map)")
            assert line == format_response(want), name
        else:
            assert line == ok(), name
    assert output[0]["drive_unknown"] == format_response(
        Err("BADPIN", "pin D99 is not in the pin map")
    )
    assert output[0]["drive_noargs"] == "ERR BADCMD DRIVE takes 2-5 arguments, got 1"


@pytest.fixture
def drive_cases(output, pinmap) -> dict[str, str]:
    cases = output[0]
    if "drive_pin" not in cases:
        pytest.skip("no wired drive pin in config/pinmap.yaml")
    m = _wired(pinmap.pins[cases["drive_pin"]].stm32)
    assert m
    cases = dict(cases)
    cases["_stm32"] = f"{m.group(1)} {int(m.group(2))}"
    return cases


def test_drive_actions_reach_the_mapped_stm32_pin(drive_cases) -> None:
    pin = drive_cases["_stm32"]  # e.g. "A 8"
    calls = {
        "drive_high": f"set {pin} 1",
        "drive_low": f"set {pin} 0",
        "drive_release": f"set {pin} 2",
        "drive_pulse": f"pulse {pin} 0 50",
        "drive_bounce": f"bounce {pin} 5 200 0",
        "drive_bounce_max": f"bounce {pin} 100 100000 1",
    }
    for case, call in calls.items():
        assert drive_cases[case] == ok(), case
        assert drive_cases[f"{case}_call"] == call, case


def test_drive_rejects_bad_arguments_without_driving(drive_cases) -> None:
    errors = {
        "drive_badlevel": Err("BADARG", "level must be HIGH, LOW or RELEASE"),
        "drive_lowercase": Err("BADARG", "level must be HIGH, LOW or RELEASE"),
        "drive_pulse_release": Err("BADARG", "level must be HIGH or LOW"),
        "drive_pulse_w0": Err("BADARG", "width_ms must be 1-10000"),
        "drive_pulse_wbig": Err("BADARG", "width_ms must be 1-10000"),
        "drive_pulse_args": Err("BADCMD", "usage: DRIVE <pin> PULSE <width_ms> HIGH|LOW"),
        "drive_bounce_c0": Err("BADARG", "count must be 1-100"),
        "drive_bounce_cbig": Err("BADARG", "count must be 1-100"),
        "drive_bounce_i9": Err("BADARG", "interval_us must be 10-100000"),
        "drive_bounce_ibig": Err("BADARG", "interval_us must be 10-100000"),
        "drive_bounce_args": Err(
            "BADCMD", "usage: DRIVE <pin> BOUNCE <count> <interval_us> HIGH|LOW"
        ),
        "drive_extra": Err("BADCMD", "usage: DRIVE <pin> HIGH|LOW|RELEASE"),
    }
    for case, err in errors.items():
        assert drive_cases[case] == format_response(err), case
        assert drive_cases[f"{case}_call"] == "-", case  # the pin was never touched


def test_drive_hardware_errors(drive_cases) -> None:
    pin_name = drive_cases["drive_pin"]
    port, num = drive_cases["_stm32"].split()
    noport = Err("INTERNAL", f"no GPIO port {port} (pin {pin_name})")
    assert drive_cases["drive_noport"] == format_response(noport)
    hw = Err("INTERNAL", f"could not drive P{port}{num}")
    assert drive_cases["drive_hw"] == format_response(hw)


# --------------------------------------------------------------------------- DELAY

EDGE_CODES = {"RISING": 1, "FALLING": 2, "ANY": 3}


def _same_line(a: str, b: str) -> bool:
    """Two pins with the same number on different ports share one STM32 edge interrupt."""
    ma, mb = _wired(a), _wired(b)
    return bool(ma and mb and int(ma.group(2)) == int(mb.group(2)) and ma.group(1) != mb.group(1))


def test_delay_checks_both_pins_against_the_pin_map(output, pinmap) -> None:
    """from_pin needs gpio, to_pin needs timer_capture, both wired (as validate.py requires)."""
    cases = output[0]
    if "delay_refs" not in cases:
        pytest.skip("pin map has no wired gpio or timer_capture pin")
    from_ref, to_ref = cases["delay_refs"].split()
    good = ok(delay_ms=3.25, to_edge_count=1)
    for side, cap, other in (("from", "gpio", to_ref), ("to", "timer_capture", from_ref)):
        for name, info in pinmap.pins.items():
            line = cases[f"delay{side}:{name}"]
            if cap not in info.caps:
                want = format_response(Err("BADPIN", f"pin {name} has no {cap} capability"))
            elif not _wired(info.stm32):
                want = format_response(
                    Err("BADPIN", f"pin {name} is not wired (TBD in the pin map)")
                )
            elif _same_line(info.stm32, pinmap.pins[other].stm32):
                a, b = (name, other) if side == "from" else (other, name)
                n = int(_wired(info.stm32).group(2))  # type: ignore[union-attr]
                want = format_response(
                    Err("BADARG", f"pins {a} and {b} share edge interrupt line {n}")
                )
            else:
                want = good
            assert line == want, (side, name)
    unknown = format_response(Err("BADPIN", "pin D99 is not in the pin map"))
    assert cases["delay_unknown_from"] == unknown
    assert cases["delay_unknown_to"] == unknown


@pytest.fixture
def delay_cases(output, pinmap) -> dict[str, str]:
    cases = output[0]
    if "delay_pins" not in cases:
        pytest.skip("pin map has no wired gpio or timer_capture pin")
    cases = dict(cases)
    from_pin, to_pin = cases["delay_pins"].split()
    mf, mt = _wired(pinmap.pins[from_pin].stm32), _wired(pinmap.pins[to_pin].stm32)
    assert mf and mt
    cases["_from"], cases["_to"] = from_pin, to_pin
    cases["_from_stm32"] = (mf.group(1), int(mf.group(2)))
    cases["_to_stm32"] = (mt.group(1), int(mt.group(2)))
    # pins the board drives are left as they are; inputs get the pull-down
    cases["_from_keep"] = int("drive" in pinmap.pins[from_pin].caps)
    cases["_to_keep"] = int("drive" in pinmap.pins[to_pin].caps)
    return cases


def test_delay_measures_through_the_mapped_stm32_pins(delay_cases) -> None:
    (fp, fn), (tp, tn) = delay_cases["_from_stm32"], delay_cases["_to_stm32"]
    fk, tk = delay_cases["_from_keep"], delay_cases["_to_keep"]
    for case, (from_edge, to_edge, timeout) in {
        "delay_basic": ("FALLING", "ANY", 100),
        "delay_rising": ("RISING", "FALLING", 50),
        "delay_any": ("ANY", "RISING", 20),
        "delay_long": ("FALLING", "ANY", 10000),
    }.items():
        want = (
            f"{fp} {fn} {EDGE_CODES[from_edge]} {fk} > "
            f"{tp} {tn} {EDGE_CODES[to_edge]} {tk} / {timeout}"
        )
        assert delay_cases[f"{case}_call"] == want, case


def test_delay_values(delay_cases) -> None:
    assert delay_cases["delay_basic"] == ok(delay_ms=3.25, to_edge_count=1)
    # microsecond resolution (99 ticks = 1.24 us), across the counter wrap
    assert delay_cases["delay_fine"] == ok(delay_ms=0.001, to_edge_count=1)
    assert delay_cases["delay_long"] == ok(delay_ms=9999.999, to_edge_count=1)
    # a bouncy response: the delay is to the first edge, every edge is counted
    assert delay_cases["delay_bounce"] == ok(delay_ms=0.4, to_edge_count=5)


def test_delay_no_response_is_a_valid_measurement(delay_cases) -> None:
    assert delay_cases["delay_null"] == ok(delay_ms=None, to_edge_count=0)


def test_delay_rig_problems_are_errors(delay_cases) -> None:
    (fp, fn), (tp, tn) = delay_cases["_from_stm32"], delay_cases["_to_stm32"]
    # the trigger may come up to max(timeout_ms, 1000 ms) after the request
    notrig = Err("TIMEOUT", f"no FALLING edge on {delay_cases['_from']} within 1000 ms")
    assert delay_cases["delay_notrigger"] == format_response(notrig)
    notrig = Err("TIMEOUT", f"no RISING edge on {delay_cases['_from']} within 2000 ms")
    assert delay_cases["delay_notrigger_long"] == format_response(notrig)
    noport = Err("INTERNAL", f"no GPIO port for P{fp}{fn} or P{tp}{tn}")
    assert delay_cases["delay_noport"] == format_response(noport)
    hw = format_response(Err("INTERNAL", f"edge interrupt setup failed on P{fp}{fn} or P{tp}{tn}"))
    assert delay_cases["delay_hw"] == hw
    assert delay_cases["delay_clock0"] == hw


def test_delay_rejects_bad_arguments_without_measuring(delay_cases) -> None:
    errors = {
        "delay_badfrom": Err("BADARG", "from_edge must be RISING, FALLING or ANY"),
        "delay_badto": Err("BADARG", "to_edge must be RISING, FALLING or ANY"),
        "delay_t0": Err("BADARG", "timeout_ms must be 1-10000"),
        "delay_tbig": Err("BADARG", "timeout_ms must be 1-10000"),
        "delay_tnan": Err("BADARG", "timeout_ms must be 1-10000"),
    }
    for case, err in errors.items():
        assert delay_cases[case] == format_response(err), case
        assert delay_cases[f"{case}_call"] == "-", case
    assert delay_cases["delay_args"] == "ERR BADCMD DELAY takes 5 arguments, got 4"


# --------------------------------------------------------------------------- UART


def _uart_row(pinmap, cap: str):
    """The pin the firmware uses: the first row (by name, as in pins_gen.h) with the cap."""
    for name in sorted(pinmap.pins):
        if cap in pinmap.pins[name].caps:
            return name, pinmap.pins[name]
    return None


@pytest.fixture
def uart_cases(output, pinmap) -> dict[str, str]:
    cases = dict(output[0])
    for cap, key in (("uart_rx", "_rx"), ("uart_tx", "_tx")):
        row = _uart_row(pinmap, cap)
        m = _wired(row[1].stm32) if row else None
        if row is None or m is None:
            pytest.skip(f"pin map has no wired {cap} pin")
        cases[key] = f"{m.group(1)} {int(m.group(2))}"
        cases[f"{key}_name"] = row[0]
        cases[f"{key}_stm32"] = f"P{m.group(1)}{int(m.group(2))}"
    return cases


def test_uart_requests_match_the_host(uart_cases) -> None:
    """The harness sends what grader.protocol sends for the same plan steps."""
    assert UartRead(9600, 200).to_line() == "UART 9600 READ 200"
    assert UartSend(9600, b"ON\n").to_line() == "UART 9600 SEND 4F4E0A"
    assert uart_cases["uart_read_on_call"] == f"read {uart_cases['_rx']} 9600 200"
    assert uart_cases["uart_send_on_call"] == f"send {uart_cases['_tx']} 9600 3 4F4E0A"


def test_uart_read_returns_the_raw_bytes(uart_cases) -> None:
    assert uart_cases["uart_read_on"] == ok(text=b"ON\r\n", byte_count=4, framing_errors=0)
    assert uart_cases["uart_read_empty"] == ok(text=b"", byte_count=0, framing_errors=0)
    # a wrong baud gives junk bytes and framing errors: still a measurement, not an error
    junk = ok(text=b"\xff\x00\xf0", byte_count=3, framing_errors=2)
    assert uart_cases["uart_read_garbage"] == junk
    assert uart_cases["uart_read_escape"] == ok(text=b'a,b"c%d e', byte_count=9, framing_errors=0)


def test_uart_long_text_is_truncated_but_counted(uart_cases) -> None:
    for case, total, byte in (("uart_read_long", 1000, None), ("uart_read_long_esc", 600, b"\n")):
        line = uart_cases[case]
        kept = len(parse_response(line).fields["text"])  # type: ignore[union-attr]
        assert len(line) <= LINE_MAX, case
        assert kept < total, case
        assert len(line) > LINE_MAX - 100, case  # most of the line is used
        data = bytes(65 + i % 26 for i in range(kept)) if byte is None else byte * kept
        want = ok(text=data, truncated=1, byte_count=total, framing_errors=0)
        assert line == want, case
    full = ok(text=b"ONOFFON", truncated=1, byte_count=30, framing_errors=0)
    assert uart_cases["uart_read_bufull"] == full


def test_uart_accepts_exactly_the_standard_bauds(uart_cases) -> None:
    for baud in STANDARD_BAUDS:
        assert uart_cases[f"uart_baud_{baud}"] == ok(text=b"ON", byte_count=2, framing_errors=0)
        assert uart_cases[f"uart_baud_{baud}_call"] == f"read {uart_cases['_rx']} {baud} 100"
    bad = format_response(
        Err(
            "BADARG",
            "baud must be 300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200 or 230400",
        )
    )
    for case in ("uart_baud_bad", "uart_baud_zero", "uart_baud_big", "uart_baud_syntax"):
        assert uart_cases[case] == bad, case
        assert uart_cases[f"{case}_call"] == "-", case


def test_uart_send(uart_cases) -> None:
    tx = uart_cases["_tx"]
    assert uart_cases["uart_send_on"] == ok()
    assert uart_cases["uart_send_lower"] == ok()
    assert uart_cases["uart_send_lower_call"] == f"send {tx} 115200 2 0A0D"
    assert uart_cases["uart_send_big"] == ok()
    assert uart_cases["uart_send_big_call"] == f"send {tx} 9600 500 0001020304050607"
    bad = format_response(Err("BADARG", "payload must be hex bytes, e.g. 48690A"))
    for case in ("uart_send_odd", "uart_send_nothex", "uart_send_0x", "uart_send_toobig"):
        assert uart_cases[case] == bad, case
        assert uart_cases[f"{case}_call"] == "-", case


def test_uart_argument_checks(uart_cases) -> None:
    window = format_response(Err("BADARG", "window_ms must be 1-10000"))
    for case in ("uart_read_w0", "uart_read_wbig", "uart_read_wsyntax"):
        assert uart_cases[case] == window, case
        assert uart_cases[f"{case}_call"] == "-", case
    mode = format_response(Err("BADARG", "mode must be SEND or READ"))
    assert uart_cases["uart_mode_bad"] == mode
    assert uart_cases["uart_mode_lower"] == mode
    assert uart_cases["uart_args"] == "ERR BADCMD UART takes 3 arguments, got 2"


def test_uart_rig_problems_are_errors(uart_cases) -> None:
    overrun = "uart overrun: bytes arrived faster than the board read them"
    assert uart_cases["uart_read_overrun"] == format_response(Err("INTERNAL", overrun))
    hw = format_response(Err("INTERNAL", "student UART setup failed"))
    assert uart_cases["uart_read_hw"] == hw
    assert uart_cases["uart_send_hw"] == hw
    for case, key in (("uart_read_nousart", "_rx"), ("uart_send_nousart", "_tx")):
        stm32, name = uart_cases[f"{key}_stm32"], uart_cases[f"{key}_name"]
        want = Err("BADPIN", f"no USART1 on {stm32} (pin {name})")
        assert uart_cases[case] == format_response(want), case


# --------------------------------------------------------------------------- ARM / COLLECT


@pytest.fixture
def arm_cases(output, pinmap) -> dict[str, str]:
    cases = dict(output[0])
    if "arm_pins" not in cases:
        pytest.skip("pin map needs two wired timer_capture pins and a wired drive pin")
    cases["_cap1"], cases["_cap2"], cases["_drv"] = cases["arm_pins"].split()
    return cases


def test_trace_leaves_a_driven_pin_alone(arm_cases) -> None:
    """TRACE on the drive pin keeps the board's own DRIVE (keep=1); inputs get the pull-down."""
    assert arm_cases["trace_drv_keep"] == "1"
    assert arm_cases["trace_in_keep"] == "0"


def test_arm_runs_the_button_sequence(arm_cases, pinmap) -> None:
    """ARM DELAY + ARM UART READ, then the press, then COLLECT both."""
    assert arm_cases["arm_delay"] == ok(slot=0)
    assert arm_cases["arm_uart"] == ok(slot=1)
    assert arm_cases["arm_press"] == ok()
    assert arm_cases["collect_delay"] == ok(delay_ms=3.25, to_edge_count=1)
    assert arm_cases["collect_uart"] == ok(text=b"ON\r\n", byte_count=4, framing_errors=0)
    # both measurements were running before the press and finished at COLLECT
    assert arm_cases["arm_button_events"] == (
        "delay_start uart_start drive delay_finish uart_finish"
    )
    # the trigger pin is the one the board drives, so it is left as it is (keep=1)
    drv = _wired(pinmap.pins[arm_cases["_drv"]].stm32)
    cap = _wired(pinmap.pins[arm_cases["_cap1"]].stm32)
    assert drv and cap
    want = f"{drv.group(1)} {int(drv.group(2))} 2 1 > {cap.group(1)} {int(cap.group(2))} 3 0 / 100"
    assert arm_cases["arm_button_delay_call"] == want


def test_collect_frees_the_slot(arm_cases) -> None:
    assert arm_cases["arm_freq"] == ok(slot=0)
    assert arm_cases["collect_freq"] == arm_cases["freq_1k"]  # the same reply as plain FREQ
    noslot = format_response(Err("NOSLOT", "slot 0 is not armed"))
    assert arm_cases["collect_again"] == noslot


def test_busy_when_the_hardware_is_in_use(arm_cases) -> None:
    cap1, cap2 = arm_cases["_cap1"], arm_cases["_cap2"]
    assert arm_cases["arm_trace"] == ok(slot=0)
    kind = format_response(Err("BUSY", "TRACE is already armed in slot 0"))
    assert arm_cases["busy_kind"] == kind
    assert arm_cases["busy_kind_now"] == kind  # a plain TRACE too
    pin = format_response(Err("BUSY", f"pin {cap2} is in use by slot 0"))
    assert arm_cases["busy_pin"] == pin
    assert arm_cases["busy_pin_delay"] == pin
    # other hardware runs next to an armed measurement
    assert arm_cases["free_other"] == arm_cases["freq_1k"], cap1
    blink = ok(edge_count=8, final_level=1, edges_ms=[100.0 + 250.0 * i for i in range(8)])
    assert arm_cases["collect_trace"] == blink


def test_uart_send_while_a_read_is_armed(arm_cases) -> None:
    assert arm_cases["arm_uart2"] == ok(slot=0)
    assert arm_cases["send_same_baud"] == ok()
    busy = Err("BUSY", "UART READ at 9600 baud is armed in slot 0")
    assert arm_cases["send_other_baud"] == format_response(busy)
    assert arm_cases["send_other_baud_call"] == "-"


def test_reset_stops_every_armed_measurement(arm_cases) -> None:
    assert arm_cases["arm_trace2"] == ok(slot=1)
    assert arm_cases["arm_reset"] == ok()
    assert arm_cases["arm_reset_events"] == "uart_cancel trace_cancel"
    noslot = format_response(Err("NOSLOT", "slot 0 is not armed"))
    assert arm_cases["collect_after_reset"] == noslot


def test_measurement_errors_arrive_at_collect(arm_cases) -> None:
    assert arm_cases["arm_notrig"] == ok(slot=0)
    notrig = Err("TIMEOUT", f"no FALLING edge on {arm_cases['_drv']} within 1000 ms")
    assert arm_cases["collect_notrig"] == format_response(notrig)


def test_arm_errors_take_no_slot(arm_cases) -> None:
    only = "only measurements can be armed (FREQ, TRACE, DELAY, UART READ), not"
    errors = {
        "arm_none": "ERR BADCMD ARM takes 1-15 arguments, got 0",
        "arm_drive": format_response(Err("BADCMD", f"{only} DRIVE")),
        "arm_send": format_response(Err("BADCMD", "only UART READ can be armed")),
        "arm_arm": format_response(Err("BADCMD", f"{only} ARM")),
        "arm_unknown": format_response(Err("BADCMD", "unknown verb JUMP")),
        "arm_arity": "ERR BADCMD FREQ takes 2 arguments, got 1",
        "arm_badarg": format_response(Err("BADARG", "window_ms must be 1-10000")),
        "arm_badpin": format_response(Err("BADPIN", "pin D99 is not in the pin map")),
    }
    for case, want in errors.items():
        assert arm_cases[case] == want, case
    assert arm_cases["arm_after_errors"] == ok(slot=0)  # none of them took a slot
    for case, slot in (("collect_bad", "4"), ("collect_word", "x")):
        noslot = Err("NOSLOT", f"slot {slot} is not armed")
        assert arm_cases[case] == format_response(noslot), case
    assert arm_cases["collect_none"] == "ERR BADCMD COLLECT takes 1 arguments, got 0"
    assert arm_cases["arm_cleanup"] == arm_cases["freq_1k"]


# --------------------------------------------------------------------------- DAC


def test_dac_checks_every_pin_against_the_pin_map(output, pinmap) -> None:
    """DAC runs only on wired pins with the dac capability."""
    for name, info in pinmap.pins.items():
        line = output[0][f"dacpin:{name}"]
        if "dac" not in info.caps:
            want = format_response(Err("BADPIN", f"pin {name} has no dac capability"))
        elif not _wired(info.stm32):
            want = format_response(Err("BADPIN", f"pin {name} is not wired (TBD in the pin map)"))
        else:
            want = ok()
        assert line == want, name
    unknown = Err("BADPIN", "pin D99 is not in the pin map")
    assert output[0]["dac_unknown"] == format_response(unknown)


@pytest.fixture
def dac_cases(output, pinmap) -> dict[str, str]:
    cases = output[0]
    if "dac_pin" not in cases:
        pytest.skip("no wired dac pin in config/pinmap.yaml")
    m = _wired(pinmap.pins[cases["dac_pin"]].stm32)
    assert m
    cases = dict(cases)
    cases["_stm32"] = f"{m.group(1)} {int(m.group(2))}"
    return cases


def test_dac_sets_the_mapped_stm32_pin(dac_cases) -> None:
    pin = dac_cases["dac_pin"]
    assert Dac(pin, 1650).to_line() == f"DAC {pin} 1650"  # what the host sends
    for case, mv in (("dac_mid", 1650), ("dac_zero", 0), ("dac_max", 3300)):
        assert dac_cases[case] == ok(), case
        assert dac_cases[f"{case}_call"] == f"{dac_cases['_stm32']} {mv}", case


def test_dac_rejects_bad_arguments_without_output(dac_cases) -> None:
    bad = format_response(Err("BADARG", "mv must be 0-3300"))
    for case in ("dac_big", "dac_neg", "dac_frac", "dac_volts"):
        assert dac_cases[case] == bad, case
        assert dac_cases[f"{case}_call"] == "-", case
    assert dac_cases["dac_args"] == "ERR BADCMD DAC takes 2 arguments, got 1"
    only = "only measurements can be armed (FREQ, TRACE, DELAY, UART READ), not DAC"
    assert dac_cases["dac_arm"] == format_response(Err("BADCMD", only))


def test_dac_hardware_errors(dac_cases) -> None:
    pin = dac_cases["dac_pin"]
    port, num = dac_cases["_stm32"].split()
    nochan = Err("BADPIN", f"no DAC output on P{port}{num} (pin {pin})")
    assert dac_cases["dac_nochannel"] == format_response(nochan)
    assert dac_cases["dac_hw"] == format_response(Err("INTERNAL", "DAC setup failed"))


def test_dac_runs_while_a_measurement_is_armed(arm_cases) -> None:
    if "arm_dac" not in arm_cases:
        pytest.skip("no wired dac pin in config/pinmap.yaml")
    assert arm_cases["arm_freq_dac"] == ok(slot=0)
    assert arm_cases["arm_dac"] == ok()
    assert arm_cases["collect_freq_dac"] == arm_cases["freq_1k"]
