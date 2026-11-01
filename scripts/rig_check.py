"""Check the link to the STM32 measuring board.

Sends raw protocol lines through the grader's own SerialTransport and parses each reply
with the grader's own parser, so this tests the same code path that grading uses.

    python scripts/rig_check.py                    # auto-detect the ST-Link, send PING
    python scripts/rig_check.py --port COM7        # pick the port yourself
    python scripts/rig_check.py "FREQ D5 100"      # PING, then any request(s)

PING always goes first; its protocol version and pin-map hash are compared with the
host's (src/grader/protocol.py and config/pinmap.yaml).

Exit code 0 if every request got an OK reply and PING matched the host, 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from grader.pinmap import load_pinmap, pinmap_hash
from grader.protocol import PROTOCOL_VERSION, Debug, Err, Ok, ProtocolError, parse_response
from grader.transport import SerialTransport, TransportError, TransportTimeout

MAX_DEBUG_LINES = 200
DEFAULT_PINMAP = Path(__file__).resolve().parent.parent / "config" / "pinmap.yaml"


def request(transport: SerialTransport, line: str, timeout_s: float) -> Ok | Err:
    """Send one request; skip '#' debug lines; return the reply."""
    transport.send_line(line)
    for _ in range(MAX_DEBUG_LINES):
        raw = transport.read_line(timeout_s)
        reply = parse_response(raw)
        if isinstance(reply, Debug):
            print(f"  {raw}")
            continue
        return reply
    raise ProtocolError(f"more than {MAX_DEBUG_LINES} debug lines and no reply")


def check_ping(reply: Ok, host_hash: str) -> bool:
    """Print the PING fields and warn about anything that doesn't match the host."""
    fw, proto, fw_hash = (reply.fields.get(k) for k in ("fw", "protocol", "pinmap"))
    print(f"  firmware {fw}, protocol {proto}, pin map {fw_hash}")
    good = True
    if proto != PROTOCOL_VERSION:
        print(f"  WARNING: firmware speaks protocol {proto}, the host speaks {PROTOCOL_VERSION}")
        good = False
    if fw_hash is None:
        print(f"  WARNING: firmware did not report a pin-map hash (host: {host_hash})")
    elif fw_hash != host_hash:
        print(f"  WARNING: firmware pin map {fw_hash} != host pin map {host_hash}; reflash")
        good = False
    else:
        print("  pin map matches the host")
    return good


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("requests", nargs="*", help="requests to send after PING")
    ap.add_argument("--port", help="serial port, e.g. COM7 (default: auto-detect ST-Link)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--timeout", type=float, default=2.0, help="seconds per reply")
    ap.add_argument("--pinmap", type=Path, default=DEFAULT_PINMAP, help="host pin map YAML")
    args = ap.parse_args(argv)
    host_hash = pinmap_hash(load_pinmap(args.pinmap))

    try:
        transport = SerialTransport(args.port, baud=args.baud)
    except TransportError as e:
        print(f"could not open the measuring board: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # pyserial raises SerialException, e.g. port already open
        print(f"could not open the port: {e}", file=sys.stderr)
        print("Is miniterm (or another program) still using it?", file=sys.stderr)
        return 1

    ok = True
    with transport:
        print(f"connected: {transport.describe()}")
        for line in ["PING", *args.requests]:
            start = time.perf_counter()
            try:
                reply = request(transport, line, args.timeout)
            except TransportTimeout:
                print(f"> {line}\n  no reply within {args.timeout:.1f} s")
                ok = False
                continue
            except ProtocolError as e:
                print(f"> {line}\n  malformed reply: {e}")
                ok = False
                continue
            ms = (time.perf_counter() - start) * 1000
            if isinstance(reply, Ok):
                print(f"> {line}\n  OK {reply.fields}  ({ms:.0f} ms)")
                if line == "PING":
                    ok = check_ping(reply, host_hash) and ok
            else:
                print(f"> {line}\n  ERR {reply.code} {reply.message}  ({ms:.0f} ms)")
                ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
