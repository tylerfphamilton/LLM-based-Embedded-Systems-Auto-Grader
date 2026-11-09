# AI Grader for Embedded Systems Assignments

UCLA M202A project (Sean Hashem, Tyler Hamilton).

An automatic grader for Arduino Nano 33 BLE Sense assignments. It flashes a student's
sketch, measures what the board actually does with a second microcontroller, decides
pass/fail for each check in a test plan, and writes a report. An LLM can optionally
draft the test plan from an assignment handout and explain failed checks.

## How it works

```
handout ──(LLM, once per assignment)──► test plan (JSON, reviewed and approved)

student sketch ──► host: compile + upload (arduino-cli) ──► Nano 33 BLE Sense
host ──► text commands over USB ──► STM32 Nucleo-L476RG ──► wired to the Nano's pins
measurements ──► pass/fail per check (plain code) ──► report (+ LLM feedback on failures)
```

- **Plans are data.** A plan is a JSON list of stimulus, wait and measure steps with
  expected values and tolerances. New assignments need a new plan, not new code.
- **The LLM never decides a verdict.** Pass/fail always comes from comparing measured
  numbers against the plan. If an LLM call fails, the report just has no feedback.
- **Rig faults are not student faults.** Timeouts and firmware errors give `ERROR`,
  never `FAIL`.

## Hardware

| Board | Role | Connection |
|---|---|---|
| Arduino Nano 33 BLE Sense | Runs the student's sketch | USB to the laptop |
| STM32 Nucleo-L476RG | Measuring board (firmware in `firmware/`) | USB to the laptop (ST-Link serial port) |

Current wiring (the source of truth is `config/pinmap.yaml`):

| Nano | Nucleo | Purpose |
|---|---|---|
| D5 | A0 (PA0) | Frequency / duty-cycle capture |
| RST | A1 (PA1) | Reset line (open-drain) |
| GND | GND | Common ground |

Firmware build and flashing: [`firmware/README.md`](firmware/README.md). Setting up
Zephyr on Windows: [`docs/zephyr_setup.md`](docs/zephyr_setup.md). You only need Zephyr
to change the firmware; grading only needs the steps below.

## Install

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev,serial,llm]"
pytest                              # no hardware or network needed
```

For real hardware you also need `arduino-cli` with the Nano core:

```powershell
arduino-cli core update-index
arduino-cli core install arduino:mbed_nano
```

For the LLM features, set `ANTHROPIC_API_KEY` in your environment and a Claude model ID
in `config/llm.yaml` (never put the key in the repo).

## Usage

**Check the rig.** `PING` reports the firmware version, protocol version and whether the
firmware's pin map matches `config/pinmap.yaml`:

```powershell
python scripts/rig_check.py
python scripts/rig_check.py RESET "WAIT 1000" "FREQ D5 100"
```

**Grade.**

```powershell
# one sketch
grader run --plan plans/pwm_1khz.json --rig serial --sketch benchmark/pwm_1khz/correct --out out/one

# a folder of sketches (add --feedback llm for LLM explanations of failures)
grader batch --plan plans/pwm_1khz.json --submissions benchmark/pwm_1khz --rig serial --out out/pwm_hw

# Nano only: compile and upload every sketch, no measuring
grader batch --plan plans/pwm_1khz.json --submissions benchmark/pwm_1khz --rig serial --flash-only --out out/flash

# no hardware: simulated measuring board
grader batch --plan plans/pwm_1khz.json --scenarios scenarios/pwm --rig fake --out out/pwm_fake
```

Ports are detected automatically; use `--port COM5 --board-port COM7` to choose them.
Each submission gets `out/<id>/report.md` (for the student), `report.json` (everything,
including the command log) and `flash.log`. A batch also writes `summary.csv`: verdict
counts, ground truth, time per submission and LLM tokens and cost.

**Plans.**

```powershell
grader make-plan --handout handouts/pwm_1khz.md --name pwm_1khz_llm   # --dry-run: no API call
# review plans/drafts/pwm_1khz_llm.draft.json, then save it as plans/pwm_1khz_llm.json
grader approve-plan plans/pwm_1khz_llm.json --by "Sean"
grader validate-plan plans/pwm_1khz_llm.json
```

`make-plan` checks the LLM's plan with the same validator as a hand-written one and sends
any errors back to the model (up to 3 attempts). Provenance (model, prompt version,
tokens) goes in `plans/<name>.meta.yaml`. `run` and `batch` warn about plans that aren't
approved or were changed after approval.

## Submissions

`--submissions DIR` treats each subfolder `X` containing `X/X.ino` as one submission
(Arduino requires the folder and sketch names to match; extra `.cpp`/`.h` files are fine).
An optional `DIR/labels.yaml` gives the ground truth, which adds bug-detection and
false-failure rates to the batch output:

```yaml
correct:         { faulty: false }
wrong_prescaler: { faulty: true, fault: wrong_prescaler }
```

## Adding an assignment

No Python changes:

1. A handout in `handouts/` (only needed for `make-plan`).
2. A plan in `plans/<assignment>.json`, written by hand or with `make-plan`.
3. Sketch folders and `labels.yaml` in `benchmark/<assignment>/`.
4. Optionally, simulated submissions in `scenarios/<assignment>/` for `--rig fake`.

A plan can only use measurements the firmware implements. `docs/protocol.md` lists the
commands; the command table in `firmware/src/cmd.c` shows which exist so far.

## Repository layout

```
src/grader/   host software: CLI, runner, protocol, transports, flasher, LLM client, planner
firmware/     STM32 measuring-board firmware (Zephyr)
config/       pinmap.yaml, rig_profile.yaml, llm.yaml
plans/        test plans, meta files, drafts/ from the LLM
handouts/     assignment handouts
benchmark/    sketch folders + labels.yaml per assignment
scenarios/    simulated submissions for the fake rig
scripts/      rig_check.py, gen_pins_h.py
docs/         protocol.md, DESIGN.md, decisions.md, zephyr_setup.md
tests/        pytest suite
```

## Development

```powershell
pytest                                  # pytest -m live also calls the real API (costs money)
ruff check . ; ruff format --check .
python scripts/gen_pins_h.py --check    # firmware pin table matches config/pinmap.yaml
grader export-schema --check            # schemas/plan.schema.json matches plan.py
```

After changing `config/pinmap.yaml`, run `python scripts/gen_pins_h.py`, then rebuild and
reflash the firmware. Otherwise the host refuses to grade because the pin maps differ.
