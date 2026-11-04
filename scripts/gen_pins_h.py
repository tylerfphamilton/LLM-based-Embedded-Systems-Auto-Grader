"""Generate the firmware's pin table (firmware/src/pins_gen.h) from config/pinmap.yaml.

    python scripts/gen_pins_h.py            # rewrite firmware/src/pins_gen.h
    python scripts/gen_pins_h.py --check    # exit 1 if the committed header is out of date

The header is plain C (no Zephyr includes): PINMAP_HASH (the same hash the host computes,
see grader.pinmap.pinmap_hash), one CAP_<NAME> bit per capability, and the PINS table.
A stm32 value that is TBD or not of the form P<port><pin> becomes port 0 ("not wired").
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import get_args

from grader.pinmap import Capability, PinMap, load_pinmap, pinmap_hash

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PINMAP = ROOT / "config" / "pinmap.yaml"
DEFAULT_OUT = ROOT / "firmware" / "src" / "pins_gen.h"
CAPS: tuple[str, ...] = get_args(Capability)  # bit n = position in the Literal

_STM32_RE = re.compile(r"P([A-K])(\d{1,2})")
# Edge interrupts (EXTI lines) are shared by pin number across ports.
_EDGE_CAPS = {"gpio", "timer_capture"}


def parse_stm32(value: str) -> tuple[str, int] | None:
    """``"PA10"`` -> ``("A", 10)``; None if TBD or unparsable (not wired)."""
    m = _STM32_RE.fullmatch(value.strip().upper())
    if not m or int(m.group(2)) > 15:
        return None
    return m.group(1), int(m.group(2))


def shared_line_warnings(pinmap: PinMap) -> list[str]:
    by_number: dict[int, list[str]] = {}
    for name, info in sorted(pinmap.pins.items()):
        where = parse_stm32(info.stm32)
        if where is not None and _EDGE_CAPS & set(info.caps):
            by_number.setdefault(where[1], []).append(f"{name} (P{where[0]}{where[1]})")
    return [
        f"warning: {' and '.join(pins)} share EXTI line {n}; only one of them can use an "
        "edge interrupt at a time."
        for n, pins in sorted(by_number.items())
        if len(pins) > 1
    ]


def _cap_macro(cap: str) -> str:
    return f"CAP_{cap.upper()}"


def render(pinmap: PinMap, source: str) -> str:
    out = [
        "/*",
        " * GENERATED FILE - DO NOT EDIT.",
        f" * Source: {source}",
        " * Regenerate: python scripts/gen_pins_h.py   (check: --check)",
        " */",
        "#ifndef GRADER_PINS_GEN_H",
        "#define GRADER_PINS_GEN_H",
        "",
        '#include "pins.h"',
        "",
        "/* First 8 hex chars of SHA-256 of the canonical pin map (host: pinmap_hash). */",
        f'#define PINMAP_HASH "{pinmap_hash(pinmap)}"',
        "",
    ]
    width = max(len(_cap_macro(c)) for c in CAPS)
    out += [f"#define {_cap_macro(c):<{width}} (1u << {n})" for n, c in enumerate(CAPS)]
    out += ["", "/* name, port letter (0 = not wired), pin number, capabilities */"]
    out.append("static const struct pin_def PINS[] = {")
    for name, info in sorted(pinmap.pins.items()):
        where = parse_stm32(info.stm32)
        port, num = (f"'{where[0]}'", where[1]) if where else ("0", 0)
        caps = " | ".join(_cap_macro(c) for c in CAPS if c in info.caps) or "0u"
        out.append(f'    {{ "{name}", {port}, {num}, {caps} }},')
    out += [
        "};",
        "",
        f"#define PINS_COUNT {len(pinmap.pins)}",
        "",
        "#endif",
        "",
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pinmap", type=Path, default=DEFAULT_PINMAP)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--check", action="store_true", help="only check that OUT is up to date")
    args = ap.parse_args(argv)

    pinmap = load_pinmap(args.pinmap)
    try:
        source = args.pinmap.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        source = args.pinmap.as_posix()
    for w in shared_line_warnings(pinmap):
        print(w, file=sys.stderr)
    text = render(pinmap, source)

    if args.check:
        current = args.out.read_text(encoding="utf-8") if args.out.exists() else ""
        if current != text:  # read_text normalises CRLF, so autocrlf checkouts still pass
            print(f"{args.out} is stale; run: python scripts/gen_pins_h.py", file=sys.stderr)
            return 1
        print(f"{args.out} is up to date (pinmap {pinmap_hash(pinmap)})")
        return 0
    args.out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {args.out} (pinmap {pinmap_hash(pinmap)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
