"""scripts/gen_pins_h.py: the committed firmware/src/pins_gen.h must match config/pinmap.yaml."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
import yaml

from grader.pinmap import PinMap, pinmap_hash

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("gen_pins_h", ROOT / "scripts" / "gen_pins_h.py")
assert _spec and _spec.loader
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def test_committed_header_is_fresh(capsys) -> None:
    assert gen.main(["--check"]) == 0, "run: python scripts/gen_pins_h.py"


def test_check_fails_when_stale(tmp_path: Path, capsys) -> None:
    out = tmp_path / "pins_gen.h"
    out.write_text("/* old */\n", encoding="utf-8")
    assert gen.main(["--check", "--out", str(out)]) == 1
    assert "is stale" in capsys.readouterr().err
    assert gen.main(["--out", str(out)]) == 0
    assert gen.main(["--check", "--out", str(out)]) == 0


def test_header_contents(pinmap) -> None:
    text = gen.render(pinmap, "config/pinmap.yaml")
    assert f'#define PINMAP_HASH "{pinmap_hash(pinmap)}"' in text
    assert "#include <zephyr" not in text
    assert "GENERATED FILE - DO NOT EDIT" in text and "python scripts/gen_pins_h.py" in text
    assert "#define CAP_RESET" in text


@pytest.mark.parametrize(
    ("value", "parsed"),
    [("PA0", ("A", 0)), ("pb15", ("B", 15)), ("TBD", None), ("PA16", None), ("A0", None)],
)
def test_parse_stm32(value: str, parsed) -> None:
    assert gen.parse_stm32(value) == parsed


def test_shared_exti_line_warning() -> None:
    pm = PinMap.model_validate(
        yaml.safe_load(
            """
            pins:
              D5: { stm32: PA0, caps: [gpio, timer_capture] }
              D6: { stm32: PB0, caps: [gpio] }
              D0: { stm32: PC0, caps: [uart_tx] }
              D2: { stm32: TBD, caps: [gpio] }
            """
        )
    )
    assert gen.shared_line_warnings(pm) == [
        "warning: D5 (PA0) and D6 (PB0) share EXTI line 0; only one of them can use an edge "
        "interrupt at a time."
    ]
