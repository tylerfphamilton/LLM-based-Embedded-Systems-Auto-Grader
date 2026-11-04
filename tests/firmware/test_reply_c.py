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
from grader.protocol import PROTOCOL_VERSION, Err, Ok, format_response, parse_response

ROOT = Path(__file__).resolve().parents[2]
FW = ROOT / "firmware" / "src"
LINE_MAX = 1024

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
            if name == "freqpin":  # "freqpin\t<pin>\t<reply>" -> case "freqpin:<pin>"
                pin, _, line = line.partition("\t")
                name = f"freqpin:{pin}"
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