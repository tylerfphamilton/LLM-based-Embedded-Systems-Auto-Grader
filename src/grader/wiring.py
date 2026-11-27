"""Wiring guide for a plan: which Nano pins to wire to which Nucleo pins, through which
resistors (D69). Plain code from the plan and the pin map, never the LLM: a wrong pin or
resistor could damage a board.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from grader.pinmap import PinMap, pinmap_hash
from grader.plan import Plan
from grader.report import md_escape

RIG_DRIVES = {"drive", "uart_tx", "dac", "reset"}  # caps where the STM32 drives the wire


class WiringError(Exception):
    """The plan uses a pin that is not wired yet (``stm32: TBD`` in the pin map)."""


@dataclass(frozen=True)
class Connection:
    nano: str
    header: str | None
    stm32: str
    series_ohms: int | None
    direction: str
    uses: tuple[str, ...]


def _step_name(step: Any, i: int) -> str:
    return f"step '{step.id}'" if getattr(step, "id", None) else f"step #{i + 1} ({step.op})"


def _button_pins(plan: Plan) -> set[str]:
    """Pins the plan presses like an active-low button: released, or bounced."""
    return {
        s.pin
        for s in plan.steps
        if s.op == "drive" and s.action in ("release", "bounce")  # type: ignore[union-attr]
    }


def _uses(step: Any, pinmap: PinMap, buttons: set[str]) -> list[tuple[str, str]]:
    """(Nano pin, what this step uses it for) for one step."""
    kind = step.primitive if step.op == "measure" else step.op
    if kind == "drive":
        what = "button input" if step.pin in buttons else "digital input"
        return [(step.pin, f"{what} (driven by the rig)")]
    if kind == "edge_delay":
        return [(step.from_pin, "delay start (edge watched)"),
                (step.to_pin, "response output (delay measured)")]  # fmt: skip
    if kind == "uart_read":
        return [(p, "Serial1 TX → rig") for p in pinmap.pins_with("uart_rx")]
    if kind == "uart_send":
        return [(p, "Serial1 RX ← rig") for p in pinmap.pins_with("uart_tx")]
    if kind in ("i2c_emu", "i2c_log"):
        return [(p, f"I2C {cap[4:].upper()} (rig is the target)")
                for cap in ("i2c_sda", "i2c_scl") for p in pinmap.pins_with(cap)]  # fmt: skip
    labels = {
        "freq_duty": "PWM output (measured)",
        "logic_trace": "digital level (traced)",
        "analog_read": "analog output (measured)",
        "dac_set": "analog input (driven by the rig)",
    }
    return [(step.pin, labels[kind])] if kind in labels else []  # wait: no pin


def _order(pin: str) -> tuple[int, int, str]:
    m = re.fullmatch(r"([DA])(\d+)", pin)
    if m:
        return (0 if m.group(1) == "D" else 1, int(m.group(2)), pin)
    return (2 if pin == "RST" else 3, 0, pin)


def plan_connections(plan: Plan, pinmap: PinMap) -> list[Connection]:
    """GND first, then one row per Nano pin the plan uses (D0.., A0.., RST).

    Raises ``WiringError`` for a pin whose ``stm32`` is ``TBD``.
    """
    buttons = _button_pins(plan)
    uses: dict[str, list[str]] = {}
    users: dict[str, list[str]] = {}
    for i, step in enumerate(plan.steps):
        for pin, use in _uses(step, pinmap, buttons):
            uses.setdefault(pin, [])
            if use not in uses[pin]:
                uses[pin].append(use)
            users.setdefault(pin, []).append(_step_name(step, i))
    # Serial1 is wired as a pair: a plan that only reads (or only sends) still gets both
    # lines, as the TX->RX checklist line describes (D69).
    uart = {"uart_rx": "Serial1 TX → rig", "uart_tx": "Serial1 RX ← rig"}
    if any(set(pinmap.caps(p)) & set(uart) for p in uses):
        for cap, label in uart.items():
            for pin in pinmap.pins_with(cap):
                if pin not in uses:
                    uses[pin] = [f"{label} (not used by this plan; wired with the pair)"]
                    users[pin] = ["the Serial1 pair"]
    if plan.setup.reset:
        for pin in pinmap.pins_with("reset"):
            uses.setdefault(pin, []).append("reset line (the rig resets the Nano)")
            users.setdefault(pin, []).append("setup.reset")
    unwired = [p for p in sorted(uses, key=_order) if pinmap.pins[p].stm32.upper() == "TBD"]
    if unwired:
        raise WiringError(
            " ".join(
                f"pin {p} is not wired yet (stm32 is TBD in the pin map), but "
                f"{', '.join(dict.fromkeys(users[p]))} uses it." for p in unwired
            )
        )  # fmt: skip
    rows = [Connection("GND", "GND", "GND", None, "common", ("ground",))]
    for pin in sorted(uses, key=_order):
        info = pinmap.pins[pin]
        direction = "rig drives" if set(info.caps) & RIG_DRIVES else "rig measures"
        found = tuple(uses[pin]) or ((info.note,) if info.note else ())
        rows.append(Connection(pin, info.header, info.stm32, info.series_ohms, direction, found))
    return rows


def _resistor(ohms: int | None) -> str:
    if not ohms:
        return "direct wire"
    value = f"{ohms // 1000} kΩ" if ohms % 1000 == 0 else f"{ohms} Ω"
    return f"{value} in series"


def render_wiring(
    plan: Plan,
    pinmap: PinMap,
    connections: list[Connection],
    *,
    plan_file: str | None = None,
    pinmap_file: str = "config/pinmap.yaml",
) -> str:
    """The Markdown guide. Deterministic: the same input gives the same text (LF)."""
    out = [
        f"# Wiring: {plan.assignment}",
        "",
        md_escape(plan.description),
        "",
        f"Plan: `{plan_file or plan.assignment + '.json'}`  ",
        f"Pin map: `{pinmap_file}` (hash `{pinmap_hash(pinmap)}`)",
        "",
        "| # | Nano 33 BLE pin | Nucleo pin (header) | STM32 | Resistor | Direction | Used for |",
        "|---|---|---|---|---|---|---|",
    ]
    for n, c in enumerate(connections, start=1):
        out.append(
            f"| {n} | {c.nano} | {c.header or '—'} | {c.stm32} | {_resistor(c.series_ohms)} | "
            f"{c.direction} | {'; '.join(c.uses)} |"
        )
    pins = {c.nano for c in connections}
    checks = [
        "Unplug both USB cables before wiring.",
        "Connect GND first.",
        "Both boards use 3.3 V logic. Never connect a Nucleo 5V or VIN pin to the Nano.",
        "Put each listed resistor in series, in the wire itself (not to ground). It limits "
        "the current if both boards drive the line at once.",
        "Leave every other Nano pin unconnected. Don't also connect a real button, LED or "
        "sensor to a listed pin.",
    ]
    if _button_pins(plan) & pins:
        checks.append(
            "The rig releases the pin when the button is not pressed; the student's "
            "`INPUT_PULLUP` holds it high. Don't add a pull-up resistor."
        )
    if any(s.op == "uart_send" or getattr(s, "primitive", "") == "uart_read" for s in plan.steps):
        for nano_tx in pinmap.pins_with("uart_rx"):
            for nano_rx in pinmap.pins_with("uart_tx"):
                tx, rx = pinmap.pins[nano_tx], pinmap.pins[nano_rx]
                checks.append(
                    f"TX goes to RX: Nano {nano_tx} (Serial1 TX) → the rig's receive pin "
                    f"(Nucleo {tx.header or '?'}, {tx.stm32}), and the rig's transmit pin "
                    f"(Nucleo {rx.header or '?'}, {rx.stm32}) → Nano {nano_rx} (Serial1 RX)."
                )
    checks += [
        "Plug both boards into the laptop: the Nano by its own USB, the Nucleo by its ST-LINK USB.",
        "Run `python scripts/rig_check.py`. It should report a matching pin map "
        f"(`pinmap={pinmap_hash(pinmap)}`). This checks the firmware, **not** the wires.",
    ]
    out += ["", "## Checklist", ""]
    out += [f"{n}. {text}" for n, text in enumerate(checks, start=1)]
    out += [
        "",
        "---",
        "",
        "*Generated by `grader wiring` from the plan and the pin map. Don't edit it by hand: "
        "change `config/pinmap.yaml` and regenerate.*",
        "",
    ]
    return "\n".join(out)


def wiring_path(plan_path: Path) -> Path:
    """``plans/<name>.json`` -> ``plans/wiring_guides/<name>.wiring.md``."""
    return plan_path.parent / "wiring_guides" / f"{plan_path.stem}.wiring.md"


def guide_text(plan: Plan, pinmap: PinMap, plan_path: Path, pinmap_path: Path) -> str:
    """The guide for the plan file at ``plan_path``. Raises ``WiringError``."""
    try:  # a repo-relative path, so the text doesn't depend on where it was run from
        pm_file = pinmap_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        pm_file = pinmap_path.as_posix()
    conns = plan_connections(plan, pinmap)
    return render_wiring(plan, pinmap, conns, plan_file=plan_path.name, pinmap_file=pm_file)


def write_wiring(
    plan: Plan, pinmap: PinMap, plan_path: Path, pinmap_path: Path, out: Path | None = None
) -> Path:
    """Write the guide to ``out``, or to ``wiring_path``. Raises ``WiringError``."""
    text = guide_text(plan, pinmap, plan_path, pinmap_path)
    target = out or wiring_path(plan_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target
