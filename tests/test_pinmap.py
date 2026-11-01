from __future__ import annotations

from pathlib import Path

import yaml

from grader.pinmap import PinMap, load_pinmap, pinmap_canonical, pinmap_hash
from grader.plan import parse_plan
from grader.validate import validate_plan

YAML = """\
# a comment
pins:
  D5:  { stm32: PA0, caps: [gpio, timer_capture] }   # trailing comment
  D2:  { stm32: TBD, caps: [drive, gpio] }
"""

REORDERED = """\
pins:
  D2:
    caps: [gpio, drive]
    stm32: TBD
  D5: {caps: [timer_capture, gpio], stm32: PA0}
"""


def _load(tmp_path: Path, name: str, text: str, newline: str = "\n") -> PinMap:
    path = tmp_path / name
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    return load_pinmap(path)


def test_canonical_form() -> None:
    pm = PinMap.model_validate(yaml.safe_load(YAML))
    assert pinmap_canonical(pm) == "D2:TBD:drive,gpio\nD5:PA0:gpio,timer_capture"


def test_hash_ignores_comments_order_and_line_endings(tmp_path: Path) -> None:
    a = _load(tmp_path, "a.yaml", YAML)
    b = _load(tmp_path, "b.yaml", REORDERED)
    c = _load(tmp_path, "c.yaml", YAML, newline="\r\n")
    h = pinmap_hash(a)
    assert len(h) == 8 and int(h, 16) >= 0
    assert pinmap_hash(b) == h
    assert pinmap_hash(c) == h


def test_hash_changes_with_wiring(tmp_path: Path) -> None:
    a = _load(tmp_path, "a.yaml", YAML)
    moved = _load(tmp_path, "b.yaml", YAML.replace("PA0", "PB0"))
    assert pinmap_hash(moved) != pinmap_hash(a)


def test_plan_may_not_use_the_reset_pin(pinmap) -> None:
    assert pinmap.caps("RST") == {"reset"}
    raw = {
        "schema_version": "0.1", "assignment": "x", "description": "x",
        "steps": [
            {"op": "drive", "id": "kick", "pin": "RST", "action": "low"},
            {"op": "measure", "id": "m", "requirement": "r", "primitive": "logic_trace",
             "pin": "RST", "window_ms": 10,
             "expect": [{"field": "edge_count", "op": "ge", "value": 1}]},
        ],
    }  # fmt: skip
    errors = validate_plan(parse_plan(raw), pinmap)
    assert errors == [
        "step 'kick': pin RST is reserved for the rig (reset) and cannot be used by a plan step.",
        "step 'm': pin RST is reserved for the rig (reset) and cannot be used by a plan step.",
    ]
