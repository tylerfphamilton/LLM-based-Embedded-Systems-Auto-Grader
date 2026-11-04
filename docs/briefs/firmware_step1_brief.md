# Task: firmware step 1: cleanups, PING handshake, reply builder, generated pin table

Read this brief, `CLAUDE.md`, `docs/protocol.md` and everything under `firmware/` before starting.

## Ground rules

- **Branch:** work on the existing `stm32-firmware` branch. Don't create other branches.
- **Do not commit, stage or push anything.** Leave every change in the working tree. The user reviews and commits. When you finish, list every file you changed or created.
- **Line endings:** this repo uses `core.autocrlf=true` on Windows. Keep each file's existing line-ending style, and don't reformat or rewrite whole files you only need to edit.
- **Keep it small.** Don't add measurement commands (`FREQ`, `DRIVE`, …) yet; that's the next step. Don't touch the LLM code.
- **Leave Tyler's code alone** apart from the specific changes below. Keep his structure (the `link.c` interrupt/queue design and the `cmd.c` command table) and his comments, apart from obvious typos in lines you're already changing.
- **Don't choose STM32 pins.** The pin assignment will be done separately in CubeMX. Keep the existing `stm32:` values in `config/pinmap.yaml`, including placeholders and `TBD`.
- The host test suite must keep passing on Windows, and `ruff check` / `ruff format --check` must stay clean.

---

## A. Cleanups

1. `src/grader/transport.py`: delete the commented-out copy of the old file at the top (about 140 lines starting `# """Line transports`). Git history keeps the old version. Also end the file with a newline.
2. `firmware/src/main.c`: fix the startup debug line, `"# grader-dw ..."` → `"# grader-fw " FW_VERSION`.

## B. Pin-map hash (shared by host and firmware)

Firmware and host must agree on the pin map, so both sides compute the same short **pin-map hash**:

- **Canonical form:** for each pin, one line `name:stm32:cap1,cap2,...`, with caps sorted. Sort the lines by pin name and join them with `\n`. Comments, key order, whitespace and CRLF/LF must **not** change the hash.
- **Hash:** the first 8 hex characters of the SHA-256 of that text.
- Put it in `pinmap.py` as `pinmap_hash(pinmap) -> str`, and test that it ignores comments, ordering and line endings.

Also add a rig-only **`RST`** entry to `config/pinmap.yaml` (`stm32: TBD`, caps `[reset]`), with a comment saying it's the open-drain line to the Nano's RST pin. Add `reset` to the `Capability` literal in `pinmap.py`. `validate.py` must not let any plan step use `RST`: plans may only reference pins whose capabilities a step actually needs, and no step needs `reset`. Add a test for that.

## C. Generated pin table: `scripts/gen_pins_h.py`

This reads `config/pinmap.yaml` and writes `firmware/src/pins_gen.h`.

- **Output:** a header that **doesn't include any Zephyr code**, so it stays plain C:
  - `#define PINMAP_HASH "xxxxxxxx"` (from B)
  - one `#define CAP_<NAME> (1u << n)` per capability
  - a `static const struct pin_def PINS[]` table of `{ "D5", 'A', 0, CAP_GPIO | CAP_TIMER_CAPTURE }`, i.e. name, port letter, pin number and caps. A `TBD` or unparsable `stm32` value is emitted as port `0`, meaning "not wired".
  - a "generated file, do not edit" banner naming the source file and the command to regenerate it
- **`--check` mode:** exit 1 if the committed header is out of date, like `grader export-schema --check`. Add a pytest that runs the check.
- **Shared interrupt lines:** STM32 edge interrupts are shared by pin number across ports. Print a **warning** (not an error) when two wired pins with `gpio` or `timer_capture` caps have the same pin number, e.g. PA0 and PB0.
- Run it and include the generated `pins_gen.h`.

**`firmware/src/pins.c` / `pins.h`:**

- `const struct pin_def *pins_find(const char *name)` returns NULL for unknown names.
- `bool pins_wired(const struct pin_def *p)` checks whether the pin is wired.
- A helper that turns a port letter into a Zephyr GPIO device with `DEVICE_DT_GET(DT_NODELABEL(gpioa))` and so on, for the ports the L476RG has.

No command uses these yet. They just need to compile. Add the new files to `firmware/CMakeLists.txt`.

## D. Reply builder: `firmware/src/reply.c` / `reply.h`

These build `OK ...` lines in the exact format of `docs/protocol.md` ("Value encoding"). **Plain C only:** no Zephyr includes, just `<stdint.h>`, `<stdio.h>`, `<string.h>`, so the code can be compiled and tested on a PC.

```c
struct reply_buf { char text[LINE_MAX + 1]; size_t len; bool overflow; };
void reply_begin(struct reply_buf *r);                              // "OK"
void reply_int(struct reply_buf *r, const char *key, int64_t v);
void reply_fixed(struct reply_buf *r, const char *key, int64_t scaled, int decimals);
                                     // reply_fixed(r, "f", 999873, 3) -> "f=999.873"; handles negatives
void reply_null(struct reply_buf *r, const char *key);
void reply_str(struct reply_buf *r, const char *key, const uint8_t *bytes, size_t n);
                                     // quoted; bytes outside 0x21-0x7E and % " , become %XX
void reply_list_fixed(struct reply_buf *r, const char *key, const int64_t *scaled, size_t n, int decimals);
                                     // stops before the line limit and then adds truncated=1
void reply_send(struct reply_buf *r, reply_fn reply);               // overflow -> sends "ERR INTERNAL reply too long"
void reply_err(reply_fn reply, const char *code, const char *msg);  // "ERR <CODE> <msg>"
```

- Use `LINE_MAX` from `link.h`, or move it to a small shared header if that keeps `reply.c` free of Zephyr. Decimals are always printed from scaled integers; never use `%f`.
- `cmd_ping` uses the builder and now replies `OK fw="0.1" protocol="0.2" pinmap="<PINMAP_HASH>"`.
- Switch the `ERR` lines in `cmd.c` to `reply_err` where that's straightforward.
- Add `docs/protocol.md` open question 1 as answered: lists are cut short and `truncated=1` is added.

**Testing `reply.c` on a PC:**

- Add `tests/firmware/test_reply_c.py`. It compiles a tiny C harness with `reply.c` using `cc`/`gcc`/`clang` if one is found, and **skips** if none is.
- The harness prints reply lines for a table of cases: ints, negative and zero fixed values, null, strings with spaces/commas/quotes/`%`/control bytes/UTF-8, empty and truncated lists, and overflow.
- The test checks each line equals what `grader.protocol.format_response()` produces for the same values. That's the proof that firmware and host agree.

## E. PING on the host side

**Protocol (`docs/protocol.md`, `protocol.py`, firmware `version.h`):**

- Add `PING` → `OK fw=<str> protocol=<str> pinmap=<str>`.
- Bump the protocol version to **0.2** in all three places, and add a short changelog line to the doc.
- Document that the host sends `PING` on connect and after any timeout.

**`protocol.py`:** add a `Ping` command to the command classes and `parse_command()`, with round-trip tests.

**`fake_rig.py`:** `FakeDevice` answers `PING` with `fw="fake"`, the current protocol version and a `pinmap` value it's given (default: the hash of the pin map the run uses; let the caller pass it in). A scenario can override this with an optional `ping:` field (`fw`, `protocol`, `pinmap`, or `error`/`silent`) for testing mismatches. `fail_command` rules must still be able to target `PING`.

**Handshake in `runner.py`:**

- **On connect** (before flashing): send `PING`.
  - **Protocol version differs, or `pinmap` differs from the host's `pinmap_hash`:** every check is `ERROR`, with a clear reason, e.g. "measuring-board firmware pin map a3f9c2e1 does not match config/pinmap.yaml b71d0e44; reflash the firmware". Don't flash.
  - **`pinmap` field missing (older firmware):** add a warning to the report and continue.
- **After any timeout** on a request:
  1. Clear stale input. Add an optional `Transport.drain()`: it's a no-op by default, clears pending lines in `FakeTransport` and calls `reset_input_buffer()` in `SerialTransport`.
  2. Send one `PING`.
  3. If it answers, continue with the next step: the timed-out step is already `ERROR`, as today.
  4. If it doesn't, mark every remaining check `ERROR` ("measuring board stopped responding") and stop sending commands.
- Log every handshake and resync in the command log and the report's `rig_faults`.

**`scripts/rig_check.py`:** after connecting, print the `PING` result. Warn if `protocol` or `pinmap` don't match the host's.

**Tests (FakeRig, no hardware):**

- handshake OK
- protocol mismatch → all ERROR and no flash
- pin-map mismatch → all ERROR
- missing `pinmap` → warning only
- timeout then a successful resync → only the timed-out step is ERROR
- timeout then a failed resync → the rest are ERROR and no further commands are sent

The existing example scenarios and batch metrics must stay the same. Check this with `grader batch` for the pwm, button and blink assignments before and after.

## F. Firmware build check

`west` and the Zephyr SDK are **not installed** on this machine. Don't try to install them or run `west`. The user will build the firmware separately in a Docker container.

- Compile everything that is plain C (`reply.c`, the generated `pins_gen.h`) with the PC's C compiler if one is available. That's what `tests/firmware/test_reply_c.py` does.
- Keep Zephyr-specific code (`pins.c` device lookups, `CMakeLists.txt`, `cmd.c` changes) to standard, documented Zephyr APIs, and keep it as small as possible.
- In your final summary, include a short **"not compiled"** list: every Zephyr-specific file or function you changed, so the user knows what to check when building in Docker.

## G. Docs

- Update `docs/protocol.md` (PING, version 0.2, the truncation answer).
- Add `docs/decisions.md` entries for any choices this brief left open.
- Add a short `firmware/README.md`: how to build and flash, how to regenerate `pins_gen.h`, and how to check the link with `python scripts/rig_check.py`.

## Definition of done

- `pytest` passes. `tests/firmware/test_reply_c.py` either runs or is skipped with a clear reason.
- `ruff check` and `ruff format --check` are clean.
- `python scripts/gen_pins_h.py --check` passes.
- Batch metrics for all three example assignments are unchanged.
- The plain-C firmware parts compile and are tested, and the summary lists the Zephyr-specific code that hasn't been compiled.
- **Nothing is committed.** The final message lists every changed or new file, explains how to verify on hardware (build, flash, then `rig_check.py` should show the pin-map hash matching), and lists any open questions.
