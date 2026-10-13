"""Pin map: student-board pin names -> measuring-board pins and capabilities.

Capabilities are named from the *measuring board's* point of view, e.g. ``uart_rx`` means
the STM32 receives on that wire (the student transmits).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

Capability = Literal[
    "gpio",
    "drive",
    "timer_capture",
    "uart_rx",
    "uart_tx",
    "analog_in",
    "dac",
    "i2c_sda",
    "i2c_scl",
]


class PinInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stm32: str
    caps: list[Capability]


class PinMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pins: dict[str, PinInfo]

    def has(self, pin: str) -> bool:
        return pin in self.pins

    def caps(self, pin: str) -> set[str]:
        return set(self.pins[pin].caps) if pin in self.pins else set()

    def pins_with(self, cap: str) -> list[str]:
        return [name for name, info in self.pins.items() if cap in info.caps]


def load_pinmap(path: str | Path) -> PinMap:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return PinMap.model_validate(data)
