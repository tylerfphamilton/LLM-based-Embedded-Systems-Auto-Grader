"""Host <-> measuring-board text protocol (draft v0.1, see docs/protocol.md).

Both directions live here so the FakeDevice can parse exactly what the runner sends and
answer in exactly the format the runner parses:

* ``Command.to_line()`` / ``parse_command()``   - requests
* ``format_response()`` / ``parse_response()``  - replies (``OK …``, ``ERR …``, ``# …``)
* ``command_for_step()``                        - plan step -> command
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, fields
from typing import Any, ClassVar

from grader import plan as p

PROTOCOL_VERSION = "0.1"


class ProtocolError(Exception):
    """A line that does not follow the protocol. Always a rig fault, never a student fault."""


# ------------------------------------------------------------------------------- values

_SAFE = frozenset(chr(c) for c in range(0x21, 0x7F)) - {"%", '"', ","}
_INT_RE = re.compile(r"-?\d+")
_FLOAT_RE = re.compile(r"-?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?")
_KEY_RE = re.compile(r"[a-z_][a-z0-9_]*")
_PCT_RE = re.compile(r"%([0-9A-Fa-f]{2})")


def encode_string(text: str | bytes) -> str:
    """Quote and percent-encode a string so it contains no spaces, quotes or commas."""
    raw = text.encode("utf-8") if isinstance(text, str) else text
    return '"' + "".join(chr(b) if chr(b) in _SAFE else f"%{b:02X}" for b in raw) + '"'


def decode_string(token: str) -> str:
    if len(token) < 2 or token[0] != '"' or token[-1] != '"':
        raise ProtocolError(f"bad string token {token!r}")
    body = token[1:-1]
    if '"' in body or "," in body:
        raise ProtocolError(f"unescaped quote or comma in string {token!r}")
    out = bytearray()
    i = 0
    while i < len(body):
        if body[i] == "%":
            m = _PCT_RE.match(body, i)
            if not m:
                raise ProtocolError(f"bad percent escape in {token!r}")
            out.append(int(m.group(1), 16))
            i += 3
        else:
            out.append(ord(body[i]))
            i += 1
    # Undecodable bytes (e.g. a student UART at the wrong baud) become U+FFFD.
    return out.decode("utf-8", errors="replace")


def _encode_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        raise ProtocolError("booleans are not part of the protocol; use 0/1")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ProtocolError(f"cannot encode non-finite float {value}")
        return repr(value)
    if isinstance(value, str | bytes):
        return encode_string(value)
    raise ProtocolError(f"cannot encode value of type {type(value).__name__}")


def encode_value(value: Any) -> str:
    if isinstance(value, list | tuple):
        return "[" + ",".join(_encode_scalar(v) for v in value) + "]"
    return _encode_scalar(value)


def _decode_scalar(token: str) -> Any:
    if token == "null":
        return None
    if token.startswith('"'):
        return decode_string(token)
    if _INT_RE.fullmatch(token):
        return int(token)
    if _FLOAT_RE.fullmatch(token):
        return float(token)
    raise ProtocolError(f"bad value {token!r}")


def decode_value(token: str) -> Any:
    if token.startswith("["):
        if not token.endswith("]"):
            raise ProtocolError(f"unterminated list {token!r}")
        inner = token[1:-1]
        return [] if inner == "" else [_decode_scalar(t) for t in inner.split(",")]
    return _decode_scalar(token)


# ---------------------------------------------------------------------------- responses


@dataclass(frozen=True)
class Ok:
    fields: dict[str, Any]


@dataclass(frozen=True)
class Err:
    code: str
    message: str = ""


@dataclass(frozen=True)
class Debug:
    text: str


Response = Ok | Err


def format_response(resp: Ok | Err | Debug) -> str:
    if isinstance(resp, Debug):
        return f"# {resp.text}"
    if isinstance(resp, Err):
        return f"ERR {resp.code} {resp.message}".rstrip()
    for key in resp.fields:
        if not _KEY_RE.fullmatch(key):
            raise ProtocolError(f"bad key {key!r}")
    return " ".join(["OK", *(f"{k}={encode_value(v)}" for k, v in resp.fields.items())])


def parse_response(line: str) -> Ok | Err | Debug:
    """Parse one reply line. Raises ProtocolError for anything malformed."""
    line = line.rstrip("\r\n")
    if line.startswith("#"):
        return Debug(line[1:].strip())
    head, _, rest = line.partition(" ")
    if head == "OK":
        values: dict[str, Any] = {}
        for token in rest.split():
            key, eq, raw = token.partition("=")
            if not eq or not _KEY_RE.fullmatch(key):
                raise ProtocolError(f"bad key=value token {token!r} in {line!r}")
            if key in values:
                raise ProtocolError(f"duplicate key {key!r} in {line!r}")
            values[key] = decode_value(raw)
        return Ok(values)
    if head == "ERR":
        code, _, message = rest.strip().partition(" ")
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", code):
            raise ProtocolError(f"ERR line without a valid code: {line!r}")
        return Err(code, message.strip())
    raise ProtocolError(f"unrecognised reply line {line!r}")


# ----------------------------------------------------------------------------- commands

_EDGES = ("rising", "falling", "any")
_LEVELS = ("high", "low")


def _int(token: str, name: str) -> int:
    try:
        return int(token, 0)
    except ValueError:
        raise ProtocolError(f"{name} must be an integer, got {token!r}") from None


def _choice(token: str, name: str, options: tuple[str, ...]) -> str:
    if token.lower() not in options:
        raise ProtocolError(f"{name} must be one of {'/'.join(o.upper() for o in options)}")
    return token.lower()


def _arity(args: list[str], n: int, usage: str) -> None:
    if len(args) != n:
        raise ProtocolError(f"usage: {usage}")


@dataclass(frozen=True)
class Command(ABC):
    VERB: ClassVar[str]
    MEASUREMENT: ClassVar[bool] = False

    @abstractmethod
    def args(self) -> list[str]: ...

    def to_line(self) -> str:
        return " ".join([self.VERB, *self.args()])

    def duration_ms(self) -> float:
        """Nominal time the board spends on this command (for timeouts and the fake clock)."""
        return 0.0

    def match_fields(self) -> dict[str, str]:
        """Lower-cased fields used by FakeRig scenario ``match`` blocks."""
        out = {"cmd": self.VERB.lower()}
        for f in fields(self):
            out[f.name] = str(getattr(self, f.name)).lower()
        return out


@dataclass(frozen=True)
class Reset(Command):
    VERB = "RESET"

    def args(self) -> list[str]:
        return []


@dataclass(frozen=True)
class Wait(Command):
    VERB = "WAIT"
    ms: int

    def args(self) -> list[str]:
        return [str(self.ms)]

    def duration_ms(self) -> float:
        return float(self.ms)


@dataclass(frozen=True)
class DriveLevel(Command):
    VERB = "DRIVE"
    pin: str
    level: str  # high | low | release

    def args(self) -> list[str]:
        return [self.pin, self.level.upper()]


@dataclass(frozen=True)
class DrivePulse(Command):
    VERB = "DRIVE"
    pin: str
    width_ms: int
    level: str

    def args(self) -> list[str]:
        return [self.pin, "PULSE", str(self.width_ms), self.level.upper()]

    def duration_ms(self) -> float:
        return float(self.width_ms)


@dataclass(frozen=True)
class DriveBounce(Command):
    VERB = "DRIVE"
    pin: str
    count: int
    interval_us: int
    final_level: str

    def args(self) -> list[str]:
        return [
            self.pin,
            "BOUNCE",
            str(self.count),
            str(self.interval_us),
            self.final_level.upper(),
        ]

    def duration_ms(self) -> float:
        return self.count * self.interval_us / 1000


@dataclass(frozen=True)
class UartSend(Command):
    VERB = "UART"
    baud: int
    payload: bytes

    def args(self) -> list[str]:
        return [str(self.baud), "SEND", self.payload.hex().upper()]

    def duration_ms(self) -> float:
        return len(self.payload) * 10 / self.baud * 1000


@dataclass(frozen=True)
class UartRead(Command):
    VERB = "UART"
    MEASUREMENT = True
    baud: int
    window_ms: int

    def args(self) -> list[str]:
        return [str(self.baud), "READ", str(self.window_ms)]

    def duration_ms(self) -> float:
        return float(self.window_ms)


@dataclass(frozen=True)
class Dac(Command):
    VERB = "DAC"
    pin: str
    mv: int

    def args(self) -> list[str]:
        return [self.pin, str(self.mv)]


@dataclass(frozen=True)
class I2cEmu(Command):
    VERB = "I2C"
    addr: int
    registers: tuple[tuple[int, int], ...]

    def args(self) -> list[str]:
        regs = ",".join(f"0x{r:02X}:0x{v:02X}" for r, v in self.registers)
        return ["EMU", f"0x{self.addr:02X}", *([regs] if regs else [])]


@dataclass(frozen=True)
class I2cLog(Command):
    VERB = "I2C"
    MEASUREMENT = True
    window_ms: int

    def args(self) -> list[str]:
        return ["LOG", str(self.window_ms)]

    def duration_ms(self) -> float:
        return float(self.window_ms)


@dataclass(frozen=True)
class Freq(Command):
    VERB = "FREQ"
    MEASUREMENT = True
    pin: str
    window_ms: int

    def args(self) -> list[str]:
        return [self.pin, str(self.window_ms)]

    def duration_ms(self) -> float:
        return float(self.window_ms)


@dataclass(frozen=True)
class Delay(Command):
    VERB = "DELAY"
    MEASUREMENT = True
    from_pin: str
    from_edge: str
    to_pin: str
    to_edge: str
    timeout_ms: int

    def args(self) -> list[str]:
        return [
            self.from_pin,
            self.from_edge.upper(),
            self.to_pin,
            self.to_edge.upper(),
            str(self.timeout_ms),
        ]

    def duration_ms(self) -> float:
        return float(self.timeout_ms)


@dataclass(frozen=True)
class Trace(Command):
    VERB = "TRACE"
    MEASUREMENT = True
    pin: str
    window_ms: int

    def args(self) -> list[str]:
        return [self.pin, str(self.window_ms)]

    def duration_ms(self) -> float:
        return float(self.window_ms)


@dataclass(frozen=True)
class Adc(Command):
    VERB = "ADC"
    MEASUREMENT = True
    pin: str
    samples: int

    def args(self) -> list[str]:
        return [self.pin, str(self.samples)]

    def duration_ms(self) -> float:
        return self.samples * 0.02


@dataclass(frozen=True)
class Arm(Command):
    """Start a measurement in the background; reply ``OK slot=<n>`` immediately."""

    VERB = "ARM"
    inner: Command

    def args(self) -> list[str]:
        return self.inner.to_line().split(" ")

    def match_fields(self) -> dict[str, str]:
        return {"cmd": "arm"}


@dataclass(frozen=True)
class Collect(Command):
    """Wait for an armed measurement to finish and return its result."""

    VERB = "COLLECT"
    slot: int

    def args(self) -> list[str]:
        return [str(self.slot)]


def parse_command(line: str) -> Command:
    """Parse a request line (used by the FakeDevice and by round-trip tests)."""
    tokens = line.strip().split()
    if not tokens:
        raise ProtocolError("empty command")
    verb, args = tokens[0].upper(), tokens[1:]
    if verb == "RESET":
        _arity(args, 0, "RESET")
        return Reset()
    if verb == "WAIT":
        _arity(args, 1, "WAIT <ms>")
        return Wait(_int(args[0], "ms"))
    if verb == "DRIVE":
        if len(args) < 2:
            raise ProtocolError("usage: DRIVE <pin> HIGH|LOW|RELEASE|PULSE|BOUNCE ...")
        pin, action, rest = args[0], args[1].upper(), args[2:]
        if action in ("HIGH", "LOW", "RELEASE"):
            _arity(rest, 0, "DRIVE <pin> HIGH|LOW|RELEASE")
            return DriveLevel(pin, action.lower())
        if action == "PULSE":
            _arity(rest, 2, "DRIVE <pin> PULSE <width_ms> HIGH|LOW")
            return DrivePulse(pin, _int(rest[0], "width_ms"), _choice(rest[1], "level", _LEVELS))
        if action == "BOUNCE":
            _arity(rest, 3, "DRIVE <pin> BOUNCE <count> <interval_us> HIGH|LOW")
            return DriveBounce(
                pin,
                _int(rest[0], "count"),
                _int(rest[1], "interval_us"),
                _choice(rest[2], "final_level", _LEVELS),
            )
        raise ProtocolError(f"unknown DRIVE action {action!r}")
    if verb == "UART":
        if len(args) != 3:
            raise ProtocolError("usage: UART <baud> SEND <hex> | UART <baud> READ <window_ms>")
        baud, mode = _int(args[0], "baud"), args[1].upper()
        if mode == "SEND":
            try:
                return UartSend(baud, bytes.fromhex(args[2]))
            except ValueError:
                raise ProtocolError("UART SEND payload must be hex") from None
        if mode == "READ":
            return UartRead(baud, _int(args[2], "window_ms"))
        raise ProtocolError(f"unknown UART mode {mode!r}")
    if verb == "DAC":
        _arity(args, 2, "DAC <pin> <mv>")
        return Dac(args[0], _int(args[1], "mv"))
    if verb == "I2C":
        if args and args[0].upper() == "EMU" and len(args) in (2, 3):
            regs: list[tuple[int, int]] = []
            for pair in args[2].split(",") if len(args) == 3 else []:
                reg, colon, val = pair.partition(":")
                if not colon:
                    raise ProtocolError(f"bad register pair {pair!r}")
                regs.append((_int(reg, "register"), _int(val, "value")))
            return I2cEmu(_int(args[1], "addr"), tuple(regs))
        if args and args[0].upper() == "LOG" and len(args) == 2:
            return I2cLog(_int(args[1], "window_ms"))
        raise ProtocolError("usage: I2C EMU <addr> [reg:val,...] | I2C LOG <window_ms>")
    if verb == "FREQ":
        _arity(args, 2, "FREQ <pin> <window_ms>")
        return Freq(args[0], _int(args[1], "window_ms"))
    if verb == "DELAY":
        _arity(args, 5, "DELAY <from_pin> <edge> <to_pin> <edge> <timeout_ms>")
        return Delay(
            args[0],
            _choice(args[1], "from_edge", _EDGES),
            args[2],
            _choice(args[3], "to_edge", _EDGES),
            _int(args[4], "timeout_ms"),
        )
    if verb == "TRACE":
        _arity(args, 2, "TRACE <pin> <window_ms>")
        return Trace(args[0], _int(args[1], "window_ms"))
    if verb == "ADC":
        _arity(args, 2, "ADC <pin> <samples>")
        return Adc(args[0], _int(args[1], "samples"))
    if verb == "ARM":
        inner = parse_command(" ".join(args))
        if not inner.MEASUREMENT:
            raise ProtocolError(f"ARM needs a measurement command, got {inner.VERB}")
        return Arm(inner)
    if verb == "COLLECT":
        _arity(args, 1, "COLLECT <slot>")
        return Collect(_int(args[0], "slot"))
    raise ProtocolError(f"unknown command {verb!r}")


# ---------------------------------------------------------------------- plan -> command


def command_for_step(step: Any) -> Command:
    """Translate one plan step (stimulus, wait or measurement) into a protocol command."""
    match step:
        case p.DriveLevelStep():
            return DriveLevel(step.pin, step.action)
        case p.DrivePulseStep():
            return DrivePulse(step.pin, step.width_ms, step.level)
        case p.DriveBounceStep():
            return DriveBounce(step.pin, step.count, step.interval_us, step.final_level)
        case p.WaitStep():
            return Wait(step.ms)
        case p.UartSendStep():
            return UartSend(step.baud, step.payload())
        case p.DacSetStep():
            return Dac(step.pin, step.mv)
        case p.I2cEmuStep():
            return I2cEmu(step.addr, tuple(step.register_items()))
        case p.FreqDutyStep():
            return Freq(step.pin, step.window_ms)
        case p.EdgeDelayStep():
            return Delay(step.from_pin, step.from_edge, step.to_pin, step.to_edge, step.timeout_ms)
        case p.LogicTraceStep():
            return Trace(step.pin, step.window_ms)
        case p.UartReadStep():
            return UartRead(step.baud, step.window_ms)
        case p.I2cLogStep():
            return I2cLog(step.window_ms)
        case p.AnalogReadStep():
            return Adc(step.pin, step.samples)
    raise TypeError(f"no command for step type {type(step).__name__}")
