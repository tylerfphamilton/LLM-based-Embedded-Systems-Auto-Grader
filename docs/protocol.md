# Host ↔ measuring-board protocol — DRAFT v0.2

> **Status: draft.** Written host-side so the host software and the FakeRig can be built
> before the hardware arrives. The firmware author owns this document from here on; any
> change must be mirrored in `src/grader/protocol.py` (and its round-trip tests).

**Version** `0.2`, in three places that must agree: this document,
`PROTOCOL_VERSION` in `src/grader/protocol.py` and in `firmware/src/version.h`
(`tests/firmware/test_reply_c.py` checks the last two).

Changelog:

* **0.2**: `PING` (firmware version, protocol version, pin-map hash); the host handshakes
  on connect and resyncs after a timeout; lists that do not fit in a line are cut short and
  marked `truncated=1`.
* **0.1**: first draft.

## Transport

* USB CDC serial from the Nucleo-L476RG's ST-Link (VID `0x0483`). The baud rate is
  nominal (115200) because it is a virtual COM port.
* ASCII, one message per line, terminated by `\n`. The host accepts an optional `\r` before
  it. Maximum line length: 1024 bytes.
* Strict request/response. The host sends one request and waits for exactly one reply
  line. The board may send any number of `#` debug lines before the reply.

## Requests

`<VERB> <args…>`, separated by single spaces. Verbs and keywords are upper case. **Pin
names are the student-board names from the plan** (`D5`, `A0`, …). The firmware maps
them to its own pins using a compiled-in copy of `config/pinmap.yaml`.

| Request | Meaning | Reply fields |
|---|---|---|
| `PING` | Handshake: is the board answering, and with which firmware? See below | `fw`, `protocol`, `pinmap` (all strings) |
| `RESET` | Pulse the student board's RESET line | — |
| `WAIT <ms>` | Board-side delay. Keeps all timing on the board | — |
| `DRIVE <pin> HIGH\|LOW\|RELEASE` | Drive the pin, or set it to high-Z | — |
| `DRIVE <pin> PULSE <width_ms> HIGH\|LOW` | Drive to the level for width_ms, then back to the previous state | — |
| `DRIVE <pin> BOUNCE <count> <interval_us> HIGH\|LOW` | Toggle `count` times, `interval_us` apart, and end at the given level (simulates switch bounce) | — |
| `UART <baud> SEND <hex>` | Send bytes to the student's Serial1 RX (payload is always hex, e.g. `48690A`) | — |
| `UART <baud> READ <window_ms>` | Receive on the student's Serial1 TX for window_ms | `text`, `byte_count`, `framing_errors` |
| `DAC <pin> <mv>` | Set the analog voltage into the student | — |
| `I2C EMU <addr> [reg:val,…]` | Configure the emulated I2C target (hex, e.g. `0x68 0x75:0x68,0x3B:0x10`) | — |
| `I2C LOG <window_ms>` | Log I2C traffic for window_ms | `read_count`, `write_count`, `transactions` |
| `FREQ <pin> <window_ms>` | Measure frequency and duty cycle over the window | `frequency_hz`, `duty_pct`, `edge_count` |
| `DELAY <from_pin> <edge> <to_pin> <edge> <timeout_ms>` | Time from the first `edge` on from_pin to the first `edge` on to_pin; `edge` = `RISING\|FALLING\|ANY` | `delay_ms`, `to_edge_count` |
| `TRACE <pin> <window_ms>` | Record edges for the window | `edge_count`, `final_level`, `edges_ms` |
| `ADC <pin> <samples>` | Sample the student's analog output | `mean_mv`, `min_mv`, `max_mv` |
| `ARM <measurement request>` | Start a measurement in the background and reply at once | `slot` |
| `COLLECT <slot>` | Block until that armed measurement finishes, then reply with its normal result | (fields of the armed measurement) |

### Measurement semantics

* `FREQ`: `edge_count` is the number of **rising** edges in the window (100 for 1 kHz
  over 100 ms). `frequency_hz` = (rising edges − 1) / time from the first to the last
  rising edge; `duty_pct` = average high time / average period, from pulses whose rising
  edge was inside the window. If fewer than 2 rising edges occur in the window, the reply
  is `frequency_hz=null duty_pct=null` with the actual `edge_count`. **No signal is a
  valid measurement, not an error.** Edges arriving faster than the board can time them
  give `ERR INTERNAL capture overrun …` (a rig fault).
* `DELAY`: `delay_ms` is measured from the first matching edge on from_pin. If from_pin
  is the pin the board is driving, this is the moment the board drove it.
  `to_edge_count` counts *every* edge of the requested kind on to_pin from that trigger
  until `timeout_ms` after it, so the reply always takes the full timeout. If to_pin never
  changes, the reply is `delay_ms=null to_edge_count=0`. This is a valid measurement; the
  board must **not** reply `ERR TIMEOUT` here. If from_pin never changes, the reply is
  `ERR TIMEOUT …`, because the rig failed to trigger.
* `TRACE`: `final_level` is `0` or `1`. `edges_ms` is relative to the start of the window.
* `UART READ`: receives the raw bytes. Bytes with framing errors are still reported
  (as received) and counted in `framing_errors`.
* `ARM` / `COLLECT`: several measurements may be armed at once (at least 4 slots).
  Slots are freed by `COLLECT` and by `RESET`. Typical sequence:
  `ARM DELAY D2 FALLING D13 ANY 100` → `OK slot=0`, `ARM UART 9600 READ 200` →
  `OK slot=1`, `DRIVE D2 BOUNCE 5 200 LOW` → `OK`, `COLLECT 0` → `OK delay_ms=…`,
  `COLLECT 1` → `OK text=…`.

### Handshake (`PING`) and resync

`PING` → `OK fw="0.1" protocol="0.2" pinmap="ceff724f"`.

* `fw`: firmware version (`FW_VERSION` in `firmware/src/version.h`).
* `protocol`: the protocol version the firmware implements.
* `pinmap`: the **pin-map hash** the firmware was built with (`PINMAP_HASH` in the
  generated `firmware/src/pins_gen.h`). Canonical form: one line
  `name:stm32:cap1,cap2,...` per pin, caps sorted, lines sorted by pin name, joined with
  `\n` (no trailing newline). The hash is the first 8 hex characters of its SHA-256.
  Comments, key order, whitespace and line endings of the YAML do not change it. The host
  computes it with `grader.pinmap.pinmap_hash`.

The host sends `PING`:

* **On connect, before flashing.** If `protocol` differs from the host's, or `pinmap`
  differs from the hash of the host's pin map, the board is running the wrong firmware:
  nothing is flashed and every check is `ERROR` ("… reflash the firmware"). If `pinmap` is
  missing (older firmware), the host adds a warning to the report (`rig_warnings`) and
  continues. If the first `PING` times out, the host resyncs (below) and asks once more.
* **After any timeout.** The host discards pending input (stale or late reply lines) and
  sends one `PING`. If it is answered, grading continues with the next step; the
  timed-out step is already `ERROR`. If not, every remaining check is `ERROR` ("the
  measuring board stopped responding") and no further command is sent.

Handshakes and resyncs are logged in the report's command log; resyncs and handshake
failures are also listed in `rig_faults`.

## Replies

Exactly one of:

```
OK [key=value ...]
ERR <CODE> [free-text message]
# free-text debug line          (any number, before the real reply; host logs and ignores)
```

### Value encoding (`OK` lines)

Every value is a single token, so a reply can be split on spaces.

| Type | Encoding | Example |
|---|---|---|
| null | `null` | `frequency_hz=null` |
| integer | decimal | `edge_count=1000` |
| float | decimal or exponent (`-1.5`, `2e-3`); no `nan`/`inf` | `delay_ms=3.25` |
| string | **double-quoted and percent-encoded**: bytes outside `0x21–0x7E`, plus `%`, `"` and `,`, are written as `%XX` | `text="ON%0D%0A"` |
| list | `[` comma-separated scalars `]`, empty list is `[]` | `edges_ms=[0.5,250.5,500.4]` |

**Long lists.** If a list does not fit in the 1024-byte line, the board keeps as many
leading elements as fit, closes the list and adds `truncated=1` right after it (at most
once per line), e.g. `OK edge_count=400 edges_ms=[123.456,…,229.456] truncated=1`. Counts
such as `edge_count` still report the full number. A reply that does not fit at all
becomes `ERR INTERNAL reply too long`.

**Firmware number formatting.** The firmware prints decimals from scaled integers (never
`%f`): trailing zeros are dropped but one decimal is kept (`999.873`, `1000.0`, `0.0`,
`-0.005`), which is what the host's `format_response` prints for the same float.

Keys match `[a-z_][a-z0-9_]*` and appear at most once per line. Invalid UTF-8 inside a
decoded string (for example a student UART at the wrong baud) is replaced with U+FFFD on
the host. It is not an error.

### Error codes

| Code | Meaning |
|---|---|
| `BADCMD` | Unknown verb or wrong argument count |
| `BADARG` | Argument out of range or wrong type |
| `BADPIN` | Pin not in the firmware's pin map, or wrong capability |
| `TIMEOUT` | The board could not complete the operation (e.g. trigger never happened) |
| `BUSY` | No free slot, or the peripheral is in use |
| `NOSLOT` | `COLLECT` of an unknown slot |
| `INTERNAL` | Firmware bug or assertion |

The host treats **every** `ERR`, every malformed line, and every missing reply (host-side
timeout) as a **rig fault**. The affected checks become `ERROR`, never `FAIL`.

## Host timeouts

For each reply, the host waits `timeouts.command_s + slack_factor × duration`, where
`duration` is the command's nominal time (window, timeout, WAIT ms…). Both values come
from `config/rig_profile.yaml`.

## Open questions for the firmware author

1. ~~Is a 1024-byte line limit enough for `UART READ` of long student output? Should the
   board truncate and add `truncated=1`?~~ **Answered (0.2):** the line limit stays at
   1024 bytes. Lists are cut short and `truncated=1` is added (see "Long lists"). Long
   `UART READ` text will follow the same rule when `UART READ` is implemented.
2. Should `transactions` be strings like `"W:0x68:0x3B"` / `"R:0x68:0x3B:6"`? (assumed)
3. ~~Should the board send a `READY fw=… protocol=0.1` banner on connect?~~ **Superseded
   (0.2):** the host sends `PING` on connect instead. The board's `# grader-fw …` startup
   line is a debug line and is ignored.
