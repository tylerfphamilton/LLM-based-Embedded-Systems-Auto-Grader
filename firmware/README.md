# Measuring-board firmware (Nucleo-L476RG, Zephyr)

Speaks the line protocol in [`docs/protocol.md`](../docs/protocol.md) over the ST-Link's
virtual COM port (USART2, 115200 baud). Right now it only implements `PING`.

| File | What it does |
|---|---|
| `src/main.c` | Startup, then loops: read a line, handle it |
| `src/link.c/.h` | Interrupt-driven host UART; complete lines are queued for the main thread |
| `src/cmd.c/.h` | Splits a request line and dispatches it through the command table |
| `src/reply.c/.h` | Builds `OK key=value …` / `ERR …` lines (plain C, tested on the PC) |
| `src/pins.c/.h` | Pin-name lookups and port → Zephyr GPIO device |
| `src/pins_gen.h` | **Generated** pin table and `PINMAP_HASH`. Do not edit |
| `src/version.h` | `FW_VERSION`, and the `PROTOCOL_VERSION` it implements |

## Build and flash

You need `west` and the Zephyr SDK (for example in a Docker container). From the repo root:

```bash
west build -b nucleo_l476rg firmware --pristine
west flash
```

If `west flash` can't reach the ST-Link (common inside Docker), copy
`build/zephyr/zephyr.bin` to the `NODE_L476RG` USB drive that the Nucleo mounts, or flash
it with STM32CubeProgrammer.

## Regenerate the pin table

`src/pins_gen.h` is generated from `config/pinmap.yaml`. Regenerate it after **every**
change to the pin map, then rebuild and reflash:

```bash
python scripts/gen_pins_h.py            # rewrite firmware/src/pins_gen.h
python scripts/gen_pins_h.py --check    # exit 1 if it is out of date (pytest runs this too)
```

The header holds `PINMAP_HASH`, the same short hash the host computes from the YAML. The
host compares it with `PING`'s `pinmap` field before grading, so firmware built from an
old pin map is caught instead of measuring the wrong pins. The script warns when two wired
`gpio`/`timer_capture` pins share an EXTI line (same pin number on different ports, e.g.
PA0 and PB0).

## Check the link

With the board plugged in and nothing else (miniterm, …) holding the port:

```bash
python scripts/rig_check.py                  # finds the ST-Link by USB VID and sends PING
python scripts/rig_check.py --port COM7      # or name the port
python scripts/rig_check.py "FREQ D5 100"    # PING, then any other request(s)
```

Expected output:

```
connected: serial:COM7
> PING
  OK {'fw': '0.1', 'protocol': '0.2', 'pinmap': 'ceff724f'}  (12 ms)
  firmware 0.1, protocol 0.2, pin map ceff724f
  pin map matches the host
```

A `WARNING` line means the firmware's protocol version or pin map differs from the host's.
Regenerate `pins_gen.h`, rebuild and reflash.

## Testing on the PC

`tests/firmware/test_reply_c.py` compiles `reply.c`, `cmd.c` and `pins_gen.h` with the
PC's C compiler (`cc`, `gcc` or `clang`) and checks every reply line against the host's
`grader.protocol.format_response`. It is skipped if no compiler is on `PATH`. `pins.c`,
`link.c` and `main.c` use Zephyr APIs and are only compiled by `west build`.
