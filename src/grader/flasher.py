"""Getting the student's sketch onto the student board."""

from __future__ import annotations

import subprocess
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from grader.transport import ARDUINO_VID, TransportError, _default_lister, find_port

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
    """Compile and upload with ``arduino-cli`` (run on a real Nano 33 BLE; mocked in tests).

    After a successful upload the Nano re-enumerates as a new USB device. ``flash`` waits
    for an Arduino port to come back, then ``settle_s`` more, so the runner's ``RESET``
    does not land right after the upload's own reset (a double reset leaves the Nano in
    its bootloader).
    """

    kind = "arduino-cli"

    def __init__(
        self,
        *,
        fqbn: str = NANO33BLE_FQBN,
        cli: str = "arduino-cli",
        port: str | None = None,
        timeout_s: float = 300.0,  # compile (a cold mbed core build can take minutes)
        upload_timeout_s: float = 60.0,  # an upload takes ~5 s; longer means it is stuck
        run: Runner = subprocess.run,
        port_lister: Callable[[], Iterable[Any]] | None = None,
        reappear_timeout_s: float = 10.0,
        settle_s: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self.fqbn, self.cli, self.port, self.timeout_s = fqbn, cli, port, timeout_s
        self.upload_timeout_s = upload_timeout_s
        self._run = run
        self._port_lister = port_lister
        self.reappear_timeout_s, self.settle_s = reappear_timeout_s, settle_s
        self._sleep, self._now = sleep, monotonic

    def _wait_for_port(self) -> bool:
        """Poll every 0.2 s until an Arduino USB port is listed; then let the board settle."""
        lister = self._port_lister or _default_lister
        deadline = self._now() + self.reappear_timeout_s
        while not any(getattr(p, "vid", None) == ARDUINO_VID for p in lister()):
            if self._now() >= deadline:
                return False
            self._sleep(0.2)
        self._sleep(self.settle_s)
        return True

    def _exec(self, args: list[str], timeout_s: float) -> tuple[int, str]:
        proc = self._run(
            [self.cli, *args],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")

    def flash(self, submission: Submission) -> FlashResult:
        if submission.sketch_dir is None:
            return FlashResult(False, "compile", "no sketch directory given")
        sketch = str(submission.sketch_dir)
        try:
            code, log = self._exec(["compile", "--fqbn", self.fqbn, sketch], self.timeout_s)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return FlashResult(False, "compile", f"could not run {self.cli}: {exc}")
        if code != 0:
            return FlashResult(False, "compile", log, student_fault=True)
        try:
            port = self.port or find_port(ARDUINO_VID, lister=self._port_lister)
            up_args = ["upload", "-p", port, "--fqbn", self.fqbn, sketch]
            code, up_log = self._exec(up_args, self.upload_timeout_s)
        except (OSError, subprocess.TimeoutExpired, TransportError) as exc:
            return FlashResult(False, "upload", f"{log}\nupload failed: {exc}")
        if code != 0:
            return FlashResult(False, "upload", log + up_log)
        if not self._wait_for_port():
            msg = (
                f"\nthe board's USB port did not come back within {self.reappear_timeout_s} s "
                "after the upload (rig fault: check the USB cable)"
            )
            return FlashResult(False, "upload", log + up_log + msg)
        return FlashResult(True, "done", log + up_log)
