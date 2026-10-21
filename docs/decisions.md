# Decisions log

Every choice the brief left open, and every place the brief was changed or interpreted.
Newest decisions go at the bottom. "Brief" means the original task brief for this repo.

## Architecture and layout

**D1. Extra modules.** Added `clock.py` (injectable `SystemClock`/`FakeClock`),
`rig_profile.py` (rig-profile model, used by both `compare` and `runner`) and `batch.py`
(batch run + metrics, kept out of `cli.py` so it is testable without the CLI). Everything
else follows the suggested layout.

**D2. `runner.run` signature.** `run(plan, submission, flasher, transport, rig_profile,
feedback=None, *, pinmap, clock=None)`. `pinmap` is required because step 1 (validation)
needs it and there is no global state. `clock` defaults to `SystemClock`.

## Plan schema

**D3. Concurrency: `concurrent_with_next: true` on a `measure` step** (not separate
`arm`/`collect` steps). Reasons: (a) one flag is harder for an LLM to get wrong than three
steps that have to be paired by id; (b) the plan stays declarative and the runner owns the
mechanics; (c) it composes: a run of consecutive concurrent measures is armed together,
followed by exactly one stimulus step. On the wire it becomes `ARM <cmd>` … stimulus …
`COLLECT <slot>`. `validate.py` rejects a concurrent measure that is not followed by a
stimulus (`drive`, `uart_send`, `dac_set`).

**D4. Brief issue: the button sequence "press while measuring delay, *then* read UART"
would miss the message.** The student prints within milliseconds of the press, so a
`uart_read` that starts after the press would see nothing. `button_toggle.json` therefore
arms *both* `edge_delay` and `uart_read` before each bounce (allowed by D3).

**D5. Nested discriminated unions.** `Step` is discriminated on `op`. `drive` is further
discriminated on `action` and `measure` on `primitive`, so each variant has exactly its
own required fields in the JSON Schema. `Expectation` is discriminated on `op`. Field
names are unchanged from the brief (`expect`, `tol_abs`, `tol_pct`, `low`/`high`, …).

**D6. Strict typing.** All plan models use `extra="forbid"` and `strict=True`, so a string
`"100"` is not silently coerced to `100`. JSON integers are still accepted for float fields.

**D7. Ids.** `id` is required on `measure` steps and optional on other steps. There is one
check per expectation, with id `<step id>.<field>` and `#2`, `#3` … appended if a step has
several expectations on the same field. Uniqueness is checked over step ids and check ids
together.

**D8. Range checks live in `validate.py`, not in the schema,** so the LLM gets sentences
like "window_ms 20000 is out of range (1–10000)" rather than pydantic messages. Ranges:
`window_ms`/`timeout_ms` 1–10000, `wait.ms` 0–60000, `boot_wait_ms` 0–10000, `mv` 0–3300,
`width_ms` 1–10000, bounce `count` 1–100, `interval_us` 10–100000, `samples` 1–10000,
I2C `addr` 0x08–0x77, registers and values 0–255. Bauds: 300 … 230400 standard set.
Structural rules (exactly one tolerance, `low <= high`, regex compiles, `data` xor `hex`)
are pydantic validators because they don't need context.

**D9. Field kinds.** `text` is a text field; `edges_ms` and `transactions` are list fields;
everything else is numeric. `validate.py` rejects ops that make no sense for the kind
(e.g. `approx` on `text`). `contains` on a list means membership. `final_level` is an
integer `0`/`1`.

**D10. Pin capabilities required:** `drive` → `drive`; `freq_duty` → `timer_capture`;
`edge_delay` → `gpio` on from_pin and `timer_capture` on to_pin; `logic_trace` → `gpio`;
`analog_read` → `analog_in`; `dac_set` → `dac`; `uart_read`/`uart_send` → some pin with
`uart_rx`/`uart_tx`; `i2c_*` → pins with `i2c_sda` and `i2c_scl`. Capabilities are named
from the **measuring board's** point of view (as in the brief's pin map, where Nano TX D1
is `uart_rx`).

**D11. `matches` uses `re.search`** (unanchored unless the regex has `^`/`$`).

## Protocol

**D12. String values are double-quoted *and* percent-encoded** (space, `%`, `"`, `,`,
and bytes outside 0x21–0x7E become `%XX`). Every value is then one space-free token, so
firmware can emit it with a trivial loop and the host can split on spaces. Lists are
`[a,b,c]` (brackets so the empty list `[]` is unambiguous); nested lists are not allowed.
`null` is a literal. See `docs/protocol.md`.

**D13. `UART SEND` payload is always hex on the wire** (`data` strings are encoded by the
host). One form is simpler for the firmware than two.

**D14. Waits are board-side (`WAIT <ms>`), including `boot_wait_ms`.** This follows
rule 4: all timing happens on the measuring board. The host never sleeps. The injected
clock only timestamps the log. With the FakeRig, `FakeClock` advances by each command's
nominal duration, so log timestamps look realistic and tests are instant.

**D15. `DELAY` semantics.** `to_edge_count` counts edges until `timeout_ms` after the
trigger. "to_pin never changed" is a valid measurement (`delay_ms=null`), not
`ERR TIMEOUT`. `ERR TIMEOUT` means the rig failed (e.g. the trigger edge never happened).
The button plan uses `timeout_ms: 100` (the brief's example used 50) so that both
latency up to 20 ms and the LED flicker from bounce fall inside the counting window.

**D16. Host reply timeout** = `timeouts.command_s + slack_factor × command duration`
(from `rig_profile.yaml`). `COLLECT` uses the armed command's duration. At most 200 `#`
debug lines are accepted per reply.

## Runner and verdicts

**D17. Rig error handling: continue.** A failed measurement makes only its own checks
`ERROR`. A failed stand-alone stimulus or wait is logged in `report.rig_faults` and the
run continues. Later checks may still be meaningful, and the report flags the fault for a
TA. Exceptions:
* **Setup failure** (`RESET`/boot `WAIT`): nothing after it is trustworthy, so every
  check is `ERROR` and no steps run.
* **Stimulus failure inside a concurrent group:** the armed measurements are still
  collected (to free the slots), but all their checks are `ERROR`, because a measurement
  around a stimulus that never happened means nothing.

**D18. Flashing.** A compile error is the student's fault, so every check is `FAIL` with
the reason "the sketch did not compile". Any other flashing problem (arduino-cli missing,
board not found, upload error) is a rig fault, so every check is `ERROR`.

**D19. Borderline zone.** Rig error at a measured value = `abs + pct% × |measured|`
from `rig_profile.yaml`; both may be given and they add. For `approx`, `le`, `ge`, `lt`,
`gt` and `in_range`, if `|measured − boundary| ≤ rig error` for any boundary, the verdict
is `BORDERLINE`. This applies on either side of the boundary. `eq`/`ne` have no
borderline zone (they are used on counts). Fields not in the profile have zero rig error,
so they are never borderline.

**D20. Null and type handling in `compare`.** `null` → `FAIL` with "nothing was measured
… (e.g. no signal)", except for `is_null`/`not_null`. A field missing from the reply, or a
value of the wrong type, means the rig is broken → `ERROR`. `compare` never raises.

**D21. NOT_GRADED** items appear in `report.checks` with ids `not_graded.<n>` and
verdict `NOT_GRADED`, so the JSON report has one uniform list. They are excluded from
"graded" totals and listed separately in Markdown.

**D22. Feedback** is requested only for `FAIL` (not BORDERLINE or ERROR). Signature:
`explain(check, plan, submission) -> str | None`.

## FakeRig scenarios

**D23. Noise format generalised.** The brief's `noise: {freq_pct, duty_abs, delay_ms}`
names fields of specific assignments, which goes against rule 1. Scenarios use
`noise: {seed, fields: {<field>: {abs|pct}}}`, the same shape as the rig profile.
Noise is uniform in ±error, drawn in sorted field order from `random.Random(seed)`, and
applied only to numeric, non-null values of the listed fields.

**D24. `responses` apply to measurement commands only.** Stimulus/`WAIT`/`RESET`
commands always reply `OK`, unless a `fail_command` rule matches. `fail_command` may be
one rule or a list. Each rule has `cmd`, an optional `match` (extra fields, e.g.
`{count: 5}`) and either `error: "ERR …"` or `silent: true` (no reply, which exercises the
host timeout). Matching compares the parsed command's fields case-insensitively, so a
scenario tests what was really sent on the wire.

**D25. Exhausted `replies` → `ERR BADCMD …`** (a rig ERROR), not "repeat last". It is
louder, so a plan/scenario mismatch cannot hide.

**D26. Extra scenario keys:** `assignment` (to pair with a plan; batch refuses a
mismatch), `description`, `debug_lines` (emit `#` lines before each reply) and
`expected_verdicts` (used by the end-to-end tests). Neither `ground_truth` nor
`expected_verdicts` is ever visible to the runner.

**D27. A measurement's result is decided at `ARM` time** in the FakeDevice, and
`COLLECT` returns it.

**D28. Example labels.** `pwm/borderline` uses 1019.8 Hz, which is inside ±2% but within
the rig error (≈0.51 Hz) of 1020 Hz, so it is labelled `faulty: false`. `pwm/rig_timeout`
is a correct submission hit by a rig fault, so it is labelled `faulty: false`.
`button/rig_stimulus_fault` (added) covers D17's concurrent-stimulus rule and `#` lines.

## Batch and CLI

**D29. Metrics.** Detection = faulty submissions with ≥ 1 `FAIL`; BORDERLINE and ERROR
do *not* count as detection. False failure = correct submissions with ≥ 1 `FAIL`.
Scenarios without `ground_truth` are excluded from both rates and counted as
"unlabelled". If the denominator is zero, the rate is `n/a`.

**D30. Output paths.** Reports go to `<out>/<submission>/report.{json,md}` and the batch
summary goes to `<out>/summary.csv` (with an `assignment` column). **Running two batches
with the same `--out` overwrites `summary.csv`**; per-submission reports don't collide
because submission ids are prefixed by assignment in the examples. Use separate `--out`
directories if you need both summaries.

**D31. Exit codes.** `0` when a run/batch completes, whatever the verdicts are. `1` for an
invalid plan (`validate-plan`, `run`, `batch`) or a stale schema (`export-schema --check`).
`2` for usage errors, scenario/plan mismatch, or a rig that cannot be opened.
`export-schema --check` was added for CI.

**D32. Report timestamps.** Fake runs stamp `started_at` with the real wall clock and then
add simulated elapsed time. Command-log `t_ms` is relative to the run start. The
determinism test compares reports with `started_at`/`finished_at` removed.

**D33. `--rig serial`** prints an "UNTESTED ON HARDWARE" warning. It uses
`SerialTransport` (auto-detects ST-Link VID `0x0483` unless `--port`) and
`ArduinoCliFlasher` (FQBN `arduino:mbed_nano:nano33ble`, auto-detects VID `0x2341` unless
`--board-port`). pyserial is imported lazily and only for this path.

**D34. Python version.** `requires-python >= 3.11` (uses `StrEnum`, `datetime.UTC`).
Tested on CPython 3.12 and 3.13 on Windows so far; not yet run on 3.11, Linux or macOS.

## LLM layer

"Brief" in this section means `docs/briefs/llm_layer_brief.md`.

**D35. SDK and API version.** The `llm` extra pins `anthropic>=2.0`. SDK 2.x sends API
version `2026-10-21` by default. `AnthropicClient` takes an injectable `sdk_factory`
(called as `factory(api_key=, timeout=, max_retries=)`), reads `ANTHROPIC_API_KEY` only in
`complete()`, and turns *any* exception from the SDK call into `LLMError`. That is broad
on purpose: an LLM failure may only remove feedback, never crash a grading run. Retries
are the SDK's own (`max_retries`); there is no retry code here.

**D36. Brief issue: `temperature: 0` is no longer possible.** Since API version
`2026-10-21` a Messages request that sends `temperature`, `top_p` or `top_k` returns a 400
on every model, and SDK 2.x no longer has the parameter. `LLMRequest.temperature` is kept
(as `float | None`, default `None`) so the record of what was asked stays explicit, but
`config/llm.yaml` sets `temperature: null` and `AnthropicClient` raises `LLMError` before
calling the API if it is not `None`. Consequence: LLM output is **not** reproducible
run-to-run. This does not touch verdicts (rule 2), but plan drafts and feedback text can
differ between runs; the raw responses are saved so a given run can be audited.

**D37. Brief issue: forced `tool_choice` is rejected by some current models.** Claude
Opus 5.5, Sonnet 5.5 and Fable 5.1 return a 400 for `tool_choice` `{"type": "tool"}`.
`force_tool: true` (the brief's behaviour, the default) sends the forced choice;
`force_tool: false` sends `{"type": "auto"}` and relies on the prompt, which names the
tool. Either way a response without the tool call is an `LLMError`. Pick the setting that
matches the model you configure; this was not verified against the live API.
