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
    sources = [Path(__file__).with_name("reply_harness.c"), FW / "reply.c", FW / "cmd.c"]
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
