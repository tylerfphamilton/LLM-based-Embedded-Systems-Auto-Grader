"""Rig profile: the measuring board's known measurement error and timeouts."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class FieldError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    abs: float = 0.0
    pct: float = 0.0

    def at(self, measured: float) -> float:
        """Rig error (absolute, in the field's unit) at a given measured value."""
        return self.abs + abs(measured) * self.pct / 100


class Timeouts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_s: float = 2.0
    slack_factor: float = 1.5


class RigProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "unnamed"
    fields: dict[str, FieldError] = Field(default_factory=dict)
    timeouts: Timeouts = Field(default_factory=Timeouts)

    def error(self, field: str, measured: float) -> float:
        fe = self.fields.get(field)
        return fe.at(measured) if fe else 0.0


def load_rig_profile(path: str | Path) -> RigProfile:
    return RigProfile.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
