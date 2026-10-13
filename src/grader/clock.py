"""Injectable clocks, so tests never sleep and timestamps are reproducible."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float:
        """Seconds since an arbitrary origin; used for command-log timestamps."""
        ...

    def wall(self) -> datetime:
        """Timezone-aware wall time; used for report start/finish stamps."""
        ...


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def wall(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    """Simulated time. The FakeDevice advances it by each command's nominal duration."""

    def __init__(self, start: datetime | None = None):
        self._start = start or datetime(2026, 1, 1, tzinfo=UTC)
        self._t = 0.0

    def advance(self, seconds: float) -> None:
        self._t += seconds

    def monotonic(self) -> float:
        return self._t

    def wall(self) -> datetime:
        return self._start + timedelta(seconds=self._t)
