"""Check the link to the STM32 measuring board.

Sends raw protocol lines through the grader's own SerialTransport and parses each reply
with the grader's own parser, so this tests the same code path that grading uses.

    python scripts/rig_check.py                    # auto-detect the ST-Link, send PING
    python scripts/rig_check.py --port COM7        # pick the port yourself
    python scripts/rig_check.py "FREQ D5 100"      # send any request(s)

Exit code 0 if every request got an OK reply, 1 otherwise.
"""

from __future__ import annotations

import argparse
import sys
import time

from grader.protocol import Debug, Err, Ok, ProtocolError, parse_response
from grader.transport import SerialTransport, TransportError, TransportTimeout

MAX_DEBUG_LINES = 200


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("requests", nargs="*", default=["PING"], help='default: "PING"')
    ap.add_argument("--port", help="serial port, e.g. COM7 (default: auto-detect ST-Link)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--timeout", type=float, default=2.0, help="seconds per reply")
    args = ap.parse_args(argv)

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
        for line in args.requests:
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
            else:
                print(f"> {line}\n  ERR {reply.code} {reply.message}  ({ms:.0f} ms)")
                ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())