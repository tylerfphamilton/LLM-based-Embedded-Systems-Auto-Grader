"""Line transports: the only thing that changes between the FakeRig and real hardware."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import deque
from collections.abc import Callable, Iterable
from typing import Any, ClassVar, Protocol

STLINK_VID = 0x0483  # Nucleo-L476RG on-board ST-Link (measuring board)
ARDUINO_VID = 0x2341  # Arduino Nano 33 BLE Sense (student board)


class TransportError(Exception):
    """The link to the measuring board failed (rig fault)."""


class TransportTimeout(TransportError):
    """No complete line arrived within the timeout (rig fault)."""


class Transport(ABC):
    kind: ClassVar[str] = "abstract"

    @abstractmethod
    def send_line(self, line: str) -> None: ...

    @abstractmethod
    def read_line(self, timeout_s: float) -> str:
        """Return one line without its terminator, or raise TransportTimeout."""

    @abstractmethod
    def close(self) -> None: ...

    def describe(self) -> str:
        return self.kind

    def __enter__(self) -> Transport:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


# ------------------------------------------------------------------------------ fake


class LineDevice(Protocol):
    def handle(self, line: str) -> list[str]:
        """Consume one request line; return the lines the device sends back (maybe none)."""
        ...


class FakeTransport(Transport):
    """In-memory transport in front of a simulated device that speaks the real protocol."""

    kind = "fake"

    def __init__(self, device: LineDevice):
        self._device = device
        self._pending: deque[str] = deque()
        self.closed = False

    def send_line(self, line: str) -> None:
        if self.closed:
            raise TransportError("transport is closed")
        if "\n" in line:
            raise TransportError("a protocol line must not contain a newline")
        self._pending.extend(self._device.handle(line))

    def read_line(self, timeout_s: float) -> str:
        if not self._pending:
            raise TransportTimeout(f"no reply within {timeout_s:.2f} s")
        return self._pending.popleft()

    def close(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------- serial


def _default_lister() -> Iterable[Any]:
    from serial.tools import list_ports  # optional dependency: pip install .[serial]

    return list_ports.comports()


def find_port(vid: int, *, lister: Callable[[], Iterable[Any]] | None = None) -> str:
    """Find the single serial port whose USB vendor id is ``vid``."""
    ports = [p for p in (lister or _default_lister)() if getattr(p, "vid", None) == vid]
    if not ports:
        raise TransportError(f"no USB serial device with VID {vid:#06x} found; is it plugged in?")
    if len(ports) > 1:
        names = ", ".join(p.device for p in ports)
        raise TransportError(f"several devices with VID {vid:#06x} ({names}); pass --port")
    return ports[0].device


class SerialTransport(Transport):
    """pyserial transport to the STM32 measuring board. UNTESTED ON HARDWARE."""

    kind = "serial"

    def __init__(
        self,
        port: str | None = None,
        *,
        baud: int = 115200,
        vid: int = STLINK_VID,
        serial_factory: Callable[..., Any] | None = None,
        port_lister: Callable[[], Iterable[Any]] | None = None,
    ):
        if serial_factory is None:
            import serial  # optional dependency: pip install .[serial]

            serial_factory = serial.Serial
        self.port = port or find_port(vid, lister=port_lister)
        self._ser = serial_factory(self.port, baudrate=baud, timeout=1.0)

    def send_line(self, line: str) -> None:
        self._ser.write((line + "\n").encode("ascii"))
        self._ser.flush()

    def read_line(self, timeout_s: float) -> str:
        self._ser.timeout = timeout_s
        raw: bytes = self._ser.readline()
        if not raw.endswith(b"\n"):
            raise TransportTimeout(f"no complete line within {timeout_s:.2f} s (got {raw!r})")
        return raw.decode("ascii", errors="replace").rstrip("\r\n")

    def close(self) -> None:
        self._ser.close()

    def describe(self) -> str:
        return f"serial:{self.port}"
