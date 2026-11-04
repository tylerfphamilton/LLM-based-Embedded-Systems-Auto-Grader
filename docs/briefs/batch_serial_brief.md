# Task: `grader batch` on real hardware (host side) + real PWM benchmark sketches

Read this brief and `CLAUDE.md` first.

## Ground rules

- **Branch:** create `batch-serial` from `main` and work there.
- **Do not commit, stage or push.** List every changed or new file at the end.
- **Keep it simple.** Aim for roughly 200 new lines of source, not counting tests and sketches. No new abstractions beyond what's described here. Prefer small changes to `batch.py`, `cli.py` and `flasher.py`.
- **Don't touch:** the firmware, the protocol, the LLM code, the existing scenario replies, or `expected_verdicts`.
- Keep each file's line endings (`core.autocrlf=true` repo). Don't reformat whole files.
- `pytest`, `ruff check` and `ruff format --check` must pass on Windows.
- **There is no STM32 attached.** There is a Nano 33 BLE Sense and `arduino-cli` with the `arduino:mbed_nano` core installed. Don't run anything that needs the STM32. You may run the `--flash-only` command in section F at the end, if a Nano is detected.

---

## A. Benchmark sketches: `benchmark/pwm_1khz/`

Final layout: one folder per submission, with the `.ino` named after the folder (Arduino's rule), plus a labels file.

```
benchmark/pwm_1khz/
  labels.yaml
  correct/correct.ino                       (existing)
  wrong_duty/wrong_duty.ino                 (existing)
  wrong_pin/wrong_pin.ino                   (existing)
  wrong_prescaler/wrong_prescaler.ino       (existing)
  borderline/borderline.ino                 NEW
  correct_alt_style/correct_alt_style.ino   NEW
```

1. **Strip the hints from the existing sketches.** Remove the `PLACEHOLDER`, `Scenario:` and `Planted bug:` header lines, and any comment that names or explains the fault. Keep comments a student would plausibly write, such as `// 1 ms period -> 1 kHz` (a misleading comment next to a wrong constant is fine and realistic). Don't change any code.
2. **`borderline`:** correct style, but the period is set so the **nominal** frequency sits just inside the +2% limit: `period_us = 981` → 1019.4 Hz, 25% duty. No comment saying it's borderline.
3. **`correct_alt_style`:** a correct 1 kHz / 25% solution written differently from `correct`. For example use `pwm.period_ms(1)` and `pwm.pulsewidth_us(250)` instead of `write(0.25f)`, with different names and structure. It should look like a different student wrote it.
4. **`labels.yaml`** (ground truth for metrics; the LLM never sees it):
   ```yaml
   correct:           { faulty: false }
   correct_alt_style: { faulty: false }
   borderline:        { faulty: false }
   wrong_duty:        { faulty: true, fault: wrong_duty }
   wrong_pin:         { faulty: true, fault: wrong_pin }
   wrong_prescaler:   { faulty: true, fault: wrong_prescaler }
   ```
5. **Link the remaining fake scenarios** so fake-rig feedback has code to read. Add `sketch:` lines only; don't change replies or `expected_verdicts`.
   - `scenarios/pwm/borderline.yaml` → `benchmark/pwm_1khz/borderline`
   - `scenarios/pwm/correct_alt_style.yaml` → `benchmark/pwm_1khz/correct_alt_style`
   - `scenarios/pwm/rig_timeout.yaml` → `benchmark/pwm_1khz/correct` (it's a rig fault, not a sketch bug)

   Also remove any `# placeholder sketch (see its header)` comments on existing `sketch:` lines.
6. **Compile all six** with `arduino-cli compile --fqbn arduino:mbed_nano:nano33ble <folder>`, and report any failures.

## B. Discovering submissions and labels (`batch.py`)

- `discover_submissions(folder) -> list[Submission]`:
  - each **immediate** subfolder `X` that contains `X/X.ino` is one submission, with id `X` and `sketch_dir` set to that folder
  - sorted by id
  - other subfolders are skipped with a printed warning
- `load_labels(folder) -> dict[str, GroundTruth]`:
  - reads `labels.yaml` if it exists, using the same `GroundTruth` model as scenarios
  - no file means every submission is unlabelled
  - a label with no matching folder gives a warning
  - a submission with no label is unlabelled (already handled by the metrics)

## C. CLI: `grader batch`

Add these options and keep the existing `--scenarios` behavior **unchanged**:

| Option | Meaning |
|---|---|
| `--rig fake\|serial` | Default `fake` |
| `--submissions DIR` | Sketch folders (section B). Required for `--rig serial` |
| `--scenarios DIR` | Existing. Required for `--rig fake` |
| `--port`, `--board-port` | STM32 and Nano ports, same as `run`. Default: auto-detect |
| `--flash-only` | Serial only: compile and upload each sketch, no measuring (section F) |

Give a clear error for an invalid combination, e.g. `--rig serial` with `--scenarios`, `--flash-only` with `--rig fake`, or missing folders.

## D. Serial batch flow (`batch.py`)

`run_serial_batch(plan, submissions, labels, *, transport, flasher, pinmap, rig_profile, out_dir, feedback, plan_warnings, cost_usd)`:

1. The CLI opens **one** `SerialTransport` for the whole batch and closes it at the end.
2. For each submission, call the existing `runner.run(...)` with that transport and an `ArduinoCliFlasher`, then write the reports exactly as fake batches do.
3. Build `BatchRow`s the same way as `run_batch`, with ground truth from `labels`. Reuse `compute_metrics`, `write_summary_csv` and `format_table` unchanged, apart from the new column in E.
4. **One bad submission doesn't stop the batch.** If `runner.run` raises, record a row with all errors and the exception message (print it too), then continue.
5. **A dead rig stops the batch.** If a submission's handshake failed (the report shows flash stage `skipped` because of the handshake), print a clear message ("measuring board not responding: check USB / firmware"), write the partial `summary.csv` and stop. Ctrl+C also writes the partial summary.

Share code with the fake `run_batch` where it's easy. Don't build a general framework.

## E. `elapsed_s` column

Add `elapsed_s` (wall-clock seconds per submission, 1 decimal place) to `BatchRow` and `summary.csv` for both fake and serial batches. Use `time.monotonic()` around each submission. It will be about 0 for fake runs, which is fine. Update the tests that check CSV columns.

## F. `--flash-only` (for testing with just the Nano)

`grader batch --plan P --submissions DIR --rig serial --flash-only --out OUT`:

- **No** `SerialTransport`, no handshake, no measurements, no LLM.
- For each submission: `flasher.flash(submission)`, then print and record `id, label, flash ok, stage, student_fault, elapsed_s`. Save the arduino-cli log to `OUT/<id>/flash.log`.
- Write `OUT/flash_summary.csv` with those columns, and print a small table plus totals (n ok / n failed, total time).

## G. `ArduinoCliFlasher` after upload (`flasher.py`)

After a **successful** upload:

1. Poll for an Arduino USB port (VID `0x2341`) every 0.2 s for up to `reappear_timeout_s` (default 10 s). The Nano re-appears as a new USB device after an upload.
2. Then sleep `settle_s` (default 1.0 s). This keeps the runner's later `RESET` from landing right after the upload's own reset, which would look like a double reset and leave the Nano in its bootloader.
3. If the port never comes back, return `FlashResult(False, "upload", ...)` with a clear message. That's a rig fault, not the student's.

Make the sleep and clock functions injectable so tests don't actually wait. Update the class docstring: compile and upload have now been run on real hardware. In `cli.py`, remove the "UNTESTED ON HARDWARE" warning from `_run_serial`.

## H. Tests (no hardware, no network)

- **Discovery:** finds `X/X.ino` folders sorted; skips folders without a matching `.ino`; ids are folder names.
- **Labels:** loads; a missing file means all unlabelled; an unknown key gives a warning.
- **CLI:** invalid option combinations exit 2 with a clear message.
- **Serial batch,** using a `FakeTransport` whose `FakeDevice` answers `PING`/`RESET`/`WAIT`/`FREQ`, and a recording fake flasher:
  - the transport is opened once
  - sketches are flashed in order
  - labels feed the metrics
  - `elapsed_s` is present
  - an exception in one submission doesn't stop the others
  - a handshake failure stops the batch and still writes `summary.csv`
- **Flash-only:** no transport is created; `flash_summary.csv` contents; a compile failure is recorded as `student_fault`.
- **Flasher:** a port that reappears after a few polls succeeds and sleeps `settle_s`; a port that never reappears gives an upload failure.
- **Unchanged behavior:** the existing fake `batch --scenarios` metrics for pwm, button and blink are unchanged apart from the new `elapsed_s` column.

## Definition of done

- `pytest` passes, and `ruff check` / `ruff format --check` are clean.
- All six PWM sketches compile.
- If a Nano is detected, run this once and include the printed table in your summary:
  ```powershell
  grader batch --plan plans/pwm_1khz.json --submissions benchmark/pwm_1khz --rig serial --flash-only --out out/flash_test
  ```
- The final message lists the changed and new files, anything you couldn't verify, and the exact command for a full serial batch once the STM32 firmware supports `WAIT` (and `RESET`):
  ```powershell
  grader batch --plan plans/pwm_1khz.json --submissions benchmark/pwm_1khz --rig serial --out out/pwm_hw --feedback llm
  ```
- Nothing is committed.
