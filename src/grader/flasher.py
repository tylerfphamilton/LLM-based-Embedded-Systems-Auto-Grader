"""Getting the student's sketch onto the student board."""

from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from grader.transport import ARDUINO_VID, TransportError, find_port

NANO33BLE_FQBN = "arduino:mbed_nano:nano33ble"


@dataclass(frozen=True)
class Submission:
    id: str
    sketch_dir: Path | None = None


@dataclass(frozen=True)
class FlashResult:
    ok: bool
    stage: str  # skipped | compile | upload | done
    log: str = ""
    student_fault: bool = False  # True only for compile errors in the student's code


class Flasher(ABC):
    kind: ClassVar[str] = "abstract"

    @abstractmethod
    def flash(self, submission: Submission) -> FlashResult: ...


class NoopFlasher(Flasher):
    """For the FakeRig: the 'submission' is simulated, there is nothing to flash."""

    kind = "noop"

    def flash(self, submission: Submission) -> FlashResult:
        return FlashResult(ok=True, stage="skipped", log="noop flasher: nothing to flash")


Runner = Callable[..., Any]  # subprocess.run-compatible


class ArduinoCliFlasher(Flasher):
    """Compile and upload with ``arduino-cli``. UNTESTED ON HARDWARE (mocked in tests)."""

    kind = "arduino-cli"

    def __init__(
        self,
        *,
        fqbn: str = NANO33BLE_FQBN,
        cli: str = "arduino-cli",
        port: str | None = None,
        timeout_s: float = 300.0,
        run: Runner = subprocess.run,
        port_lister: Callable[[], Iterable[Any]] | None = None,
    ):
        self.fqbn, self.cli, self.port, self.timeout_s = fqbn, cli, port, timeout_s
        self._run = run
        self._port_lister = port_lister

    def _exec(self, args: list[str]) -> tuple[int, str]:
        proc = self._run(
            [self.cli, *args],
            capture_output=True,
            text=True,
            timeout=self.timeout_s,
            check=False,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")

    def flash(self, submission: Submission) -> FlashResult:
        if submission.sketch_dir is None:
            return FlashResult(False, "compile", "no sketch directory given")
        sketch = str(submission.sketch_dir)
        try:
            code, log = self._exec(["compile", "--fqbn", self.fqbn, sketch])
        except (OSError, subprocess.TimeoutExpired) as exc:
            return FlashResult(False, "compile", f"could not run {self.cli}: {exc}")
        if code != 0:
            return FlashResult(False, "compile", log, student_fault=True)
        try:
            port = self.port or find_port(ARDUINO_VID, lister=self._port_lister)
            code, up_log = self._exec(["upload", "-p", port, "--fqbn", self.fqbn, sketch])
        except (OSError, subprocess.TimeoutExpired, TransportError) as exc:
            return FlashResult(False, "upload", f"{log}\nupload failed: {exc}")
        if code != 0:
            return FlashResult(False, "upload", log + up_log)
        return FlashResult(True, "done", log + up_log)
