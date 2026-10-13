from __future__ import annotations

from pathlib import Path

import pytest

from grader.pinmap import PinMap, load_pinmap
from grader.rig_profile import RigProfile, load_rig_profile

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def root() -> Path:
    return ROOT


@pytest.fixture(scope="session")
def pinmap() -> PinMap:
    return load_pinmap(ROOT / "config" / "pinmap.yaml")


@pytest.fixture(scope="session")
def rig_profile() -> RigProfile:
    return load_rig_profile(ROOT / "config" / "rig_profile.yaml")
