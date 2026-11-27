# Task: a wiring guide for every plan (generated from the plan and the pin map)

Read this brief, `CLAUDE.md`, `config/pinmap.yaml`, `src/grader/pinmap.py`,
`scripts/gen_pins_h.py` and `docs/decisions.md` (D59, D68) before starting.

## Why

We don't have a fixed wiring harness. Whoever sets up the rig (a TA, or us) wires the Nano
33 BLE Sense to the Nucleo-L476RG by hand for each assignment. A wiring guide next to each
plan says exactly which wires to connect, through which resistors, so a wrong wire is
caught before grading.

**The guide is made by plain code, never by the LLM.** Every connection follows from the
plan's pins and `config/pinmap.yaml`, so code can produce it exactly. An LLM could invent a
wrong pin or resistor, and a wrong resistor can damage a board.

## Ground rules

- **No new branch:** work on the current branch (`main`).
- **Do not commit, stage or push.** List every changed or new file at the end.
- **Leave unrelated changes alone.** The working tree already has uncommitted changes (for
  example under `benchmark/blink_2hz/` and `.gitignore`). Don't modify, revert or reformat
  them.
- **Keep it simple.** Aim for roughly 150 new lines of source, not counting tests and docs.
  No templating library and no diagrams.
- **Don't touch:** the firmware, the protocol, existing plans, or grading behavior.
- Keep each file's line endings (`core.autocrlf=true` repo). Don't reformat whole files.
- `pytest`, `ruff check`, `ruff format --check` and `python scripts/gen_pins_h.py --check`
  must pass on Windows. No network calls in tests.

---

## A. Wiring facts move into the pin map

Today the Nucleo header labels and the series resistors are only comments in
`config/pinmap.yaml` (`# Nucleo D7, via 1 kOhm`). Make them fields:

```yaml
D2:  { stm32: PA8, caps: [gpio, drive], header: D7, series_ohms: 1000,
       note: "STM32 drives the student's button input" }
```

- **`header`** (string, optional): the label printed on the Nucleo board next to the pin,
  for example `A0`, `D7` or `D3`. Take it from the existing comments; leave it out where the
  comment doesn't give one.
- **`series_ohms`** (integer, optional): the resistor in series on that wire. Today that's
  1000 on D2 and D0, from the comments. A missing value means a direct wire.
- **`note`** (string, optional): one short purpose line, taken from the existing comment.
- Add the fields to `PinInfo` in `pinmap.py`.
- **The pin-map hash must not change.** `pinmap_canonical` uses only name, `stm32` and caps,
  so the firmware doesn't need a reflash. Add a test that the hash of the committed
  `pinmap.yaml` is unchanged by this edit. Use the value before your change, which is in
  `firmware/src/pins_gen.h`.
- Keep the comments that say something the fields don't. Don't change any `stm32` or caps
  value.
- `gen_pins_h.py` must still work and `--check` must still pass. If it reads the YAML
  directly, make sure the new fields don't break it.

## B. Which connections a plan needs: `wiring.py`

Add `src/grader/wiring.py` with `plan_connections(plan, pinmap) -> list[Connection]`.

**Pins each step uses:**

| Step | Nano pins |
|---|---|
| `drive` (any action) | `pin` |
| `freq_duty`, `logic_trace`, `analog_read` | `pin` |
| `edge_delay` | `from_pin`, `to_pin` |
| `uart_read` | the pin(s) with the `uart_rx` capability |
| `uart_send` | the pin(s) with the `uart_tx` capability |
| `dac_set` | `pin` |
| `i2c_emu`, `i2c_log` | the pins with `i2c_sda` and `i2c_scl` |

**Always add:**

- **GND to GND**, listed first.
- **The reset line** (the pin with the `reset` capability) when `plan.setup.reset` is true.

**Rules:**

- **One row per Nano pin,** sorted after the GND row: digital pins (`D0`…) in number order,
  then analog (`A0`…), then `RST`. A row records:
  - the Nano pin;
  - the Nucleo header and STM32 pin;
  - `series_ohms`;
  - what the plan uses the pin for, e.g. "button input (driven by the rig)", "LED (traced)",
    "Serial1 TX → rig", "Serial1 RX ← rig", "PWM output (measured)". Derive these from the
    caps and steps; fall back to the pin map's `note`.
- **The direction:** "rig drives" for `drive`, `uart_tx`, `dac` and `reset` pins, otherwise
  "rig measures".
- **A pin whose `stm32` is `TBD`** (not wired) is an error: raise `WiringError` naming the pin
  and the steps that use it. The validator may accept such a plan today, but it can't be
  wired.
- **Per-student plans** (`params`) need no special handling. Pins never contain
  placeholders.

## C. The guide: `render_wiring(plan, pinmap, connections) -> str`

Markdown, written next to the plan as `plans/<name>.wiring.md`. It must be
**deterministic**: no dates, the same input gives byte-identical output (LF line endings
inside the string; the writer handles the rest).

**Contents:**

1. **Title:** `# Wiring: <assignment>`, with the plan's description and file name, and
   `Pin map: config/pinmap.yaml (hash <pinmap_hash>)`. The hash lets the TA compare it with
   the `pinmap=` value that `python scripts/rig_check.py` prints.
2. **A table:**

   | # | Nano 33 BLE pin | Nucleo pin (header) | STM32 | Resistor | Direction | Used for |
   |---|---|---|---|---|---|---|

   The resistor column shows `1 kΩ in series` or `direct wire`.
3. **A checklist.** Fixed text, plus lines that depend on the plan:
   - Unplug both USB cables before wiring.
   - Connect GND first.
   - Both boards use 3.3 V logic. Never connect a Nucleo 5V or VIN pin to the Nano.
   - Put each listed resistor in series, in the wire itself (not to ground). It limits the
     current if both boards drive the line at once.
   - Leave every other Nano pin unconnected. Don't also connect a real button, LED or
     sensor to a listed pin.
   - Plug both boards into the laptop: the Nano by its own USB, the Nucleo by its ST-LINK
     USB.
   - Run `python scripts/rig_check.py`. It should report a matching pin map. Note in the
     guide that it checks the firmware, **not** the wires.
   - **If the plan drives a button pin** (an active-low input), add: "The rig releases the
     pin when the button is not pressed; the student's `INPUT_PULLUP` holds it high. Don't
     add a pull-up resistor."
   - **If the plan uses `uart_*`**, add a line saying TX goes to RX: Nano D1 (Serial1 TX) →
     the rig's receive pin, and the rig's transmit pin → Nano D0 (Serial1 RX).
4. A footer: *"Generated by `grader wiring` from the plan and the pin map. Don't edit it by
   hand: change `config/pinmap.yaml` and regenerate."*

## D. Commands

- **`grader wiring --plan P [--pinmap ...] [--out FILE] [--print]`:**
  - writes `plans/<name>.wiring.md` next to the plan by default, or to `--out FILE`;
  - `--print` writes to stdout instead;
  - validates the plan first, as `run` does;
  - a `WiringError` exits 2 with the message.
- **`grader make-plan`:** after writing the plan (D68), also write its wiring guide and print
  the path. If the guide fails (a TBD pin), keep the plan, print the error clearly, and exit
  2, so the user knows the plan can't be wired yet.
- **Generate guides for the hand-written plans:** `blink_2hz`, `pwm_1khz`, `button_toggle`
  and `uart_id`. Don't generate them for the LLM plans; they get one when regenerated or
  through `grader wiring`.

## E. Tests (no hardware, no network)

- **Pins per step:**
  - **per primitive:** each primitive in section B adds the right pins (a small hand-made
    plan per case);
  - **always-on rows:** GND is always there and listed first; RST only appears when
    `setup.reset` is true;
  - **duplicates:** a pin used by several steps appears once, with each of its uses;
  - **order:** digital pins in number order, then analog, then RST.
- **Resistors:** for `button_toggle.json`, D2 and D0 show `1 kΩ in series`, and D13 and D1
  show `direct wire`.
- **The full guide:** for `uart_id.json`, the TX→RX line is present; for `button_toggle.json`,
  the button note is present; for `pwm_1khz.json`, neither is.
- **A TBD pin:** a plan using `A0` raises `WiringError` naming `A0` and the step. Use a temp
  plan, because A0 is still TBD.
- **Deterministic:** rendering twice gives identical text. The committed guides for the four
  hand plans equal a fresh render; make this a test, like `gen_pins_h.py --check`.
- **Pin map:** the hash is unchanged; the new fields load; an unknown field is still
  rejected (`extra="forbid"`).
- **CLI:**
  - `grader wiring --plan plans/button_toggle.json --print` exits 0 and contains the table;
  - `make-plan` with `FakeLLMClient` writes `plans/<name>.wiring.md` next to the plan;
  - a TBD pin keeps the plan and exits 2.

## Definition of done

- `pytest`, `ruff check`, `ruff format --check` and `python scripts/gen_pins_h.py --check`
  pass; `grader wiring --help` works.
- `plans/blink_2hz.wiring.md`, `plans/pwm_1khz.wiring.md`, `plans/button_toggle.wiring.md`
  and `plans/uart_id.wiring.md` exist and match a fresh render.
- `README.md` gets a short "Wiring" section: `grader wiring`, and that `make-plan` writes the
  guide too. `CLAUDE.md` gets the rule: wiring guides come from the plan and the pin map in
  plain code, never from the LLM; physical wiring facts live in `config/pinmap.yaml`.
- `docs/decisions.md` gets an entry:
  - why plain code and not the LLM;
  - the new pin-map fields and the unchanged hash;
  - TBD pins are an error;
  - any choice this brief left open.
- The final message lists:
  - every changed or new file;
  - the rendered `plans/button_toggle.wiring.md`, pasted in full so the user can check it
    against the real boards;
  - anything that couldn't be verified, in particular which `header` labels came from
    comments and which are missing.
- Nothing is committed.
