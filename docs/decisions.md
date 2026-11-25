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

**D22. Feedback** (superseded by D43) is requested only for `FAIL` (not BORDERLINE or ERROR). Signature:
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
The default is therefore `force_tool: false`, which sends `{"type": "auto"}` and relies on
the prompt, which names the tool. `force_tool: true` sends the brief's forced choice, for
models that accept it. A response without the tool call raises `NoToolCallError` (a
subclass of `LLMError` that carries the response). `make-plan` retries it (D39); for
feedback it is an ordinary LLM failure, so the report just has no feedback. Not verified
against the live API.

**D38. Unverified: does the API accept the pydantic plan schema as `input_schema`?** The
`submit_plan` tool sends `Plan.model_json_schema()` minus the top-level `$schema` key.
It uses `$defs`/`$ref`, `oneOf` with pydantic's OpenAPI-style `discriminator` objects,
`anyOf`, `const`, `enum`, `pattern`, `patternProperties`, `minItems`, `default` and
`title`. The tool is **not** marked `strict: true` (strict mode needs
`additionalProperties: false` everywhere and rejects some of these keywords), so the API
should treat it as an ordinary JSON Schema and ignore `discriminator`. That has not been
tried without a key. `--dry-run` only checks that the schema is a JSON object schema and
prints its size (≈18 KB, ≈4.5 k tokens). The live test `test_live_make_plan` is the
check. If the API rejects the schema, the smallest fix is to strip `discriminator` keys
in `planner.plan_tool()`. Our own `parse_plan` + `validate_plan` stay the real gate either way.

**D39. Repair loop details.** At most 3 calls. After a bad attempt the conversation gets
the model's own assistant turn, *unchanged* (all content blocks, including any thinking
blocks), then a user turn with one `tool_result` (`is_error: true`) whose content is the
error sentences joined by `\n`. The history is only ever appended to. An extra check
beyond the validator: `assignment` must equal `--name`, because the plan file name has
to match it. An answer without a `submit_plan` call (`NoToolCallError`, likely with
`force_tool: false`) uses up an attempt like a validation error. Its content (if any) is
appended as the assistant turn, followed by the user text "Call submit_plan with the
complete plan." There is no `tool_result` in that case, because there is no `tool_use`
id to answer. Any other `LLMError` (no key, API error) stops the loop at once (exit 2). On failure only `plans/drafts/<name>.log.json`
is written (no draft, no meta). `make-plan` refuses to replace a meta file whose status
is `approved` unless `--force` is given, so drafting again can't silently revoke an
approval.

**D40. Brief change: `plan_sha256` hashes the file bytes with CRLF normalised to LF.**
This repo has `core.autocrlf=true` on Windows, so the same committed plan has different
bytes on Windows and Linux checkouts. Hashing exact bytes would make every approval look
"edited" on the other OS. Only line endings are normalised; any other byte change counts
as an edit. The same normalisation is used for `handout_sha256` and for the prompt
version.

**D41. Approval check.** `approve-plan` validates the plan (schema + pin map, exit 1 on
errors) before writing anything. An existing meta file keeps its provenance fields
(`source: llm`, model, attempts …); only `status`, `approved_by`, `approved_at` and
`plan_sha256` change. `run` and `batch` call `approval_warnings()` for the plan path,
print each warning in yellow on stderr, and store them in `report.json` as
`plan_warnings`. They are not shown in the student `report.md`, because they are for TAs.
They never block a run. The runner receives them as data (`plan_warnings=`), since it
gets a `Plan` and not a path.

**D42. Scenario → sketch links.** `sketch:` is a directory path relative to the repo
root. `grade_scenario`/`run_batch` take `repo_root` (default `.`, i.e. run from the repo
root like every other default path in the CLI). The FakeRig never flashes the sketch
(`NoopFlasher`); it is used only as feedback input. The four placeholder sketches in
`benchmark/pwm_1khz/` use `mbed::PwmOut` with explicit `PRESCALER`/`COUNTER_TOP`
constants, so each planted bug is one readable line. **Not compiled:** `arduino-cli` is
not installed on the development machine. Compile them with
`arduino-cli compile --fqbn arduino:mbed_nano:nano33ble benchmark/pwm_1khz/<name>` before
relying on them. The mock handouts `handouts/pwm_1khz.md` and `handouts/button_toggle.md`
were added in step 2 because the `--dry-run` test needs one. They deliberately give no
frequency/duty tolerance, no latency number ("quickly") and no boot time, so a generated
plan has to fill `assumptions`.

**D43. Feedback hook (replaces D22).** `explain_all(checks, plan, submission,
command_log) -> FeedbackResult` is called once per submission, after every verdict is
final, and only if at least one check is `FAIL`. Its texts and code locations are
attached to FAIL checks only. An item for a BORDERLINE, ERROR or PASS check is dropped
like any unknown id. `FeedbackResult` has `texts`, `code_locations`, `llm: LLMInfo | None`
and `raw` (written to `out/<submission>/llm_feedback.json`; excluded from `report.json` so
the student code isn't duplicated there). `LLMFeedback` catches `LLMError` only; anything
else is a bug and should be loud.

**D44. Feedback input and item checks.** Failed checks go to the model as JSON
(`check_id`, `requirement`, `expected` text, `expected_value`, `measured`, `reason`), so
the values it must cite are unambiguous. At most 10 passed checks are listed by
requirement only. Command-log lines are the `tx` lines equal to a failed step's command
(or `ARM <command>`, plus the `COLLECT <slot>` that slot reply names) and their
`rx`/`debug` replies; identical commands from other steps are included too (harmless,
e.g. press 1 and press 2 of the button plan). Source: `*.ino/*.cpp/*.h` under
`sketch_dir` (recursive, sorted), numbered `   N| `, capped at 40 000 characters in total
with a visible truncation marker and a warning. A literal `</student_code>` in the source
is rewritten to `<\/student_code>`, so the code can't close its own block. An item is
dropped, with a warning, if it is malformed, names a check that isn't a FAIL, repeats a
check id, or its `cited_value` matches no element of that check's `measured` or
`expected` value (lists are flattened, so `in_range` bounds and `edges_ms` elements
count). Numbers compare at 3 significant figures. When the check's value is a number, a
cited string that *starts* with a number counts as that number, so "500 Hz", "25.1%" and
"500" match 500. "about 500 Hz" does not, because the number is not leading. The schema
still allows strings because text checks (`ON`, regexes) need them. Everything else needs
exact equality, and `null` matches a `null` measurement ("no signal"). `cause_found` is now used in the report (D58).

**D45. `--feedback llm` preflight.** `run` and `batch` check the model setting
(not the placeholder) and `ANTHROPIC_API_KEY` right after the plan validates and before
any grading or output. A failure exits 2 with one sentence. The feedback Markdown is now
`md_escape`d (it is model output) and gets a "Where to look:" line when there is a code
location.

**D46. Size: over the ~600-line target.** New source (excluding prompts and tests) is
about 915 net lines (`git diff --numstat`). About 775 of them are not blank, comments,
docstrings or lone closing brackets. llm.py is ≈180, planner.py ≈220 and feedback.py ≈230
(non-blank, non-comment); the CLI is +130. Reasons: `ruff format` puts every argument of
the CLI options and of the tool-schema/meta dict literals on its own line (≈150 lines);
the brief's plain-code item checks (D44) and step-log extraction are ≈90 lines; and
`approve-plan`/provenance is in the same files. No caching, async, retries or provider
abstraction was added. I chose not to compress the code just to hit the number. The
candidates if it has to shrink: inline `FEEDBACK_TOOL_DEF` as compact JSON, and drop
`step_log` in favour of sending the whole (short) command log.

**D47. Not verified without an API key** (all covered only by fakes):
1. That the API accepts the pydantic plan schema as `input_schema` (D38).
2. Which current models accept forced `tool_choice` (D37); `force_tool` must match the
   configured model.
3. The SDK response → `raw` conversion (`Message.to_dict()`), and that sending
   `raw["content"]` back as the assistant turn in the repair loop is accepted. That
   matters most when the model returns thinking blocks.
4. Prompt quality: whether plans validate within 3 attempts, and whether feedback items
   cite values in a form that passes D44's checks.
5. Real token counts and latency. `--dry-run`'s estimate is characters ÷ 4 (≈5.5 k input
   tokens for `pwm_1khz`, most of it the schema).
6. That the placeholder sketches compile (D42).
The two `@pytest.mark.live` tests cover items 1, 3 and part of 4 once a key and a model
are set.

## Firmware step 1: PING handshake, pin table, reply builder

**D48. Pin-map hash details.** Lines are sorted with Python's default string order (by
code point, so `D13` comes before `D2`), and the `stm32` value is used exactly as written,
including `TBD`. Wiring a `TBD` pin therefore changes the hash, which is intended: the
firmware must be rebuilt. The firmware never computes the hash. It embeds the value that
`scripts/gen_pins_h.py` computed with the host's own `pinmap_hash`, so the two cannot
drift apart.

**D49. Rig-only pins are marked by capability, not by name.** `pinmap.RIG_ONLY_CAPS =
{"reset"}`. `validate._check_pin` rejects any step whose pin has a rig-only capability,
with its own message ("pin RST is reserved for the rig (reset) and cannot be used by a
plan step."), before the usual "lacks the '…' capability" check. No step type needs
`reset`, so the normal capability check would reject `RST` anyway; the explicit message
is clearer for people and for the LLM repair loop. Nothing in Python names `RST`.

**D50. Handshake outcomes.**
* The connect `PING` goes through the normal request path, so a timeout triggers a resync.
  If the resync `PING` is answered, the host sends `PING` once more to get the fields: the
  ST-Link can lose the first bytes after the port opens. If the board never answers, or
  answers `ERR`, every check is `ERROR` and nothing is flashed.
* `protocol` must equal `PROTOCOL_VERSION` exactly (string compare). A missing `protocol`
  counts as a mismatch. A missing `pinmap` is only a warning.
* When the handshake blocks grading, `report.flash` is `ok=false, stage="skipped"`.
* Warnings go in a new `Report.rig_warnings` list, not in `rig_faults`. A warning is not a
  fault, and the end-to-end rule-3 check reads `rig_faults`.
* A successful handshake is logged only in the command log (the `PING` line, its reply
  and a `handshake: {...}` note). `rig_faults` gets handshake *failures* and every resync
  (a resync always follows a timeout, which is a fault). The brief's "log every handshake
  and resync in … `rig_faults`" is read this way so that a normal run has no faults, and so
  that the existing scenarios' `rig_faults` (for example the two in
  `button/rig_stimulus_fault`) do not change.

**D51. A dead board stops the run.** `RigClient.alive` goes false when a resync `PING`
is not answered. After that, `RigClient.request` raises without sending anything. That
covers the rest of a concurrent group already in progress. `_execute` then stops and
marks every check not measured yet `ERROR` with "rig error: the measuring board stopped
responding". Setup (`RESET`/boot `WAIT`) keeps D17's rule: if it fails, every check is
`ERROR`.

**D52. FakeRig handshake knobs.**
* `FakeDevice(..., pinmap_hash=...)` sets the `pinmap` it reports. `grade_scenario` passes
  the hash of the run's pin map. If it is not given (None), the field is left out, like
  older firmware, so a forgotten caller gets a warning, not a false mismatch.
* Scenario `ping:` overrides fields (`fw`, `protocol`, `pinmap`) or makes `PING` fail
  (`error` / `silent: true`). A field set to `null` is left out of the reply. The fields
  default to `fw="fake"`, the host's protocol version and the device's hash.
* `fail_command` rules got `after: N`: the first N matching commands are answered
  normally. This is needed to test "answers the connect `PING`, then stops responding". It
  is a general knob, not specific to `PING`.

**D53. Generated pin table layout.**
* `CAP_<NAME>` bit n is the capability's position in the `Capability` literal. **Add new
  capabilities at the end**; inserting one in the middle renumbers the bits (harmless
  after regenerating, but noisy in diffs).
* `struct pin_def` is defined in `pins.h`, which is plain C and forward-declares
  `struct device`. Only `pins.c` includes `pins_gen.h`, because the `static` table would
  otherwise be copied into every file and trigger unused-variable warnings. `pins.c`
  exports `pins_map_hash[]` for `cmd_ping`.
* The `stm32` parser accepts `P<A–K><0–15>`. Anything else (`TBD`, typos) means "not
  wired" (port `0`). `pins_port_device` covers the ports on the L476RG's LQFP64 package
  (A, B, C, D, H), each behind `DT_NODE_HAS_STATUS(…, okay)`.
* The shared-EXTI warning goes to stderr and does not change the exit code, including
  with `--check`.

**D54. Reply builder details.**
* `struct reply_buf` has one field more than the brief listed: `truncated`. It keeps
  `truncated=1` to once per line (a duplicate key would be a protocol error) when two
  lists are cut.
* Numbers are formatted by hand from integers. No `printf` is used, because 64-bit
  `%lld` support depends on the Zephyr libc configuration. `reply_fixed` drops trailing
  zeros but keeps one decimal, so its output equals Python's `repr(float)` for the same
  value as long as 1e-4 ≤ |x| < 1e16. Outside that range Python switches to exponent
  form while the firmware keeps plain decimals. Both forms are valid protocol, and the PC
  test stays inside the range. `decimals` is clamped to 0–18.
* `reply_err` cuts the message to fit the line. `cmd.c`'s message buffer `REPLY_MAX`
  dropped from 1100 to 128, because it now holds only the message part. That saves about
  1 KB of the 4 KB main stack, which `cmd_ping`'s `reply_buf` now uses.
* `cmd.c` turned out to be plain C, so the PC harness links the real `cmd.c` and tests
  `PING` and the `BADCMD` replies end to end. The harness defines `pins_map_hash` itself,
  because `pins.c` is Zephyr code.

**D55. Ruff clean-up outside the brief's list.** `ruff check` was already failing before
this step: the same kind of commented-out old copy as in `transport.py` (195 lines at the
top of `tests/test_fake_rig.py`) and missing final newlines in that file and in
`scripts/rig_check.py`. I removed the commented-out block (git history keeps it) and added
the newlines, so the brief's "ruff stays clean" can hold.

**D56. `rig_check.py` always sends `PING` first.** Extra requests on the command line
follow it, and the default request list is now empty. The exit code is 1 if `protocol` or
`pinmap` mismatch. A missing `pinmap` only prints a warning.

**D57. Batches of real sketch folders (`grader batch --rig serial`).**
* A submission is an immediate subfolder `X` with `X/X.ino`; ground truth for metrics lives
  in `labels.yaml` next to them (same `GroundTruth` model as scenarios) and is read only
  after grading.
* One `SerialTransport` for the whole batch. An exception while grading one submission
  becomes a row with every check counted as ERROR (`BatchRow.error` holds the message) and
  the batch goes on. A failed handshake (flash stage `skipped`) means the rig is dead: the
  batch stops. `summary.csv` is written in a `finally`, so a stop or Ctrl+C leaves a
  partial summary.
* `--flash-only` compiles and uploads only, writes `flash_summary.csv`, and refuses
  `--feedback llm` because nothing is graded. `--rig serial` refuses `--scenarios` and
  `--rig fake` refuses `--submissions` instead of silently ignoring them.
* `ArduinoCliFlasher` waits after a successful upload for an Arduino USB port (VID
  `0x2341`, polled every 0.2 s for up to 10 s), then `settle_s` = 1 s, so the runner's
  `RESET` does not double-reset the Nano into its bootloader. A port that never returns is
  an upload (rig) failure, not a student fault. This checks for *any* Arduino port, not the
  same port name, because Windows may renumber it.
* `summary.csv` gains `elapsed_s` (wall clock per submission, `time.monotonic()`, also for
  fake batches, where it is about 0).
* The benchmark sketches no longer name their fault (`test_scenario_sketch_links_exist`
  now checks this), so the LLM cannot read the answer from a comment.
* `tests/firmware/test_reply_c.py` was missing its final newline (as in D55), so I added it to keep `ruff check` clean.

**D58. Feedback: one explanation per root cause, and "possible causes" for no signal.**
* Each feedback item has a new required field, `same_cause_as` (a check id or null). When
  several checks fail for one reason, the model explains the cause fully once, and the
  other items get one sentence that points to it. This cuts output tokens on no-signal
  failures, where frequency and duty fail together. A reference is ignored, with a warning,
  if it points at the item itself, at a check with no accepted item, or at an item that
  has a reference of its own. The item's own explanation is kept either way.
* When the measurement is only "no signal", the prompt asks for the top two or three
  candidate causes with `cause_found: false`, unless the code clearly establishes one.
  This is because both wrong diagnoses in the Nov 10 run (submissions 05 and 06) were
  confident single answers for no-signal failures. A measured wrong value still gets one
  firm diagnosis.
* `cause_found` and `same_cause_as` are now stored on `CheckResult`, so they appear in
  `report.json`. An item that refers to another check copies that check's `cause_found`.
  In `report.md`, `cause_found: false` changes the label from "Feedback" to "Possible
  causes", and a referring item starts with "Same cause as *requirement* (`field`)."

**D59. The validator rejects concurrent groups the firmware refuses.** Tyler's ARM/COLLECT
firmware answers `ERR BUSY`/`ERR BADCMD` for some combinations, which would only show up
at run time as ERROR checks. `validate.py` now rejects them, so `make-plan`'s repair loop
fixes them before a run:
* at most 4 measure steps before one stimulus, only `edge_delay`, `freq_duty`,
  `logic_trace` and `uart_read`, at most one of each, and no shared pins;
* `edge_delay`/`logic_trace` pins with the same STM32 pin number on different ports
  (PA3/PB3, one edge-interrupt line), also for a single `edge_delay`;
* a `uart_send` stimulus at a different baud from an armed `uart_read`;
* an `edge_delay` whose `from_pin` has the `drive` capability must be concurrent, with a
  drive step on that pin as its stimulus. Otherwise the board never drives the pin and
  the delay always times out.
The plan prompt gained the matching facts, plus: an active-low button is "not pressed"
when released (never driven high, which hides a missing `INPUT_PULLUP`), and a bouncy
press uses an odd `count` (an even one adds an edge first). `plans/button_toggle.json`
now waits 1000 ms after reset, like the other plans.

**D60. Setup releases every drive pin before RESET.** `RESET` only pulses the Nano's reset
line; a pin the STM32 drives keeps its state. A plan that ended with the button pressed
(`button_toggle_sonnet_a` ends on a bounce to LOW) left D2 low for the next submission, so
that sketch booted with the button held: polled sketches toggled the LED during boot and
then printed OFF on the first press, and correct sketches failed. The runner now sends
`DRIVE <pin> RELEASE` for every wired pin with the `drive` capability (pin map, not TBD)
before the reset, whatever the plan does. Releasing in the firmware's `RESET` as well
would also work; the host-side fix needs no reflash.

**D61. Opus writes plans, Sonnet writes feedback.** `config/llm.yaml` takes
`model: {plan: ..., feedback: ...}` (a plain `model: X` still means X for both). On the
button assignment, two Opus drafts both had sound stimulus structure (settling time
before every press, every press bounced and timed, releases checked separately) and no
false fails on hardware; both Sonnet drafts left too little time between a release and
the next press (about 10 ms, so a debounce longer than that would false-fail) and timed
only one press. Opus also used fewer output tokens per plan (3.0-3.3k vs 6.6-10.7k). A
plan is made once per assignment and reviewed, so the larger model's price hardly
matters; feedback runs once per failing submission, so it stays on Sonnet. Both are
small samples (two drafts each). `price_per_mtok` prices the feedback model only, since
only batch output reports cost. `max_tokens.plan` is now 32000.

**D62. Button stimuli: long bounces, a bouncy release, and an explicit pull-up check
(instead of an open-drain rig).** On the 17-sketch button benchmark, a 0.8 ms bounce
(5 x 200 us) hid a debounce measured in microseconds (`submission_05`): `Serial1.println`
probably blocks about 4 ms at 9600 baud, so the bounce is over before the loop reads the pin
again. A clean release hid a sketch that toggles on release bounce (`submission_07`), and a
bouncy release on the push-pull rig ends with D2 driven high, which charges the floating
line and hides a missing pull-up (`submission_08`). The rig stays push-pull. Instead the plan
prompt and `plans/button_toggle.json` now:
* bounce every press and at least one release for at least 5 ms (7 changes, 1 ms apart);
* check the pull-up once: release D2 straight from LOW, then trace D2 for 50 ms and expect
  `final_level` 1 (TRACE leaves a drive pin as DRIVE set it, with no pull of its own).
Keeping push-pull means every press starts by driving D2 high, so the press delay check
always has its trigger edge, even without a pull-up (an open-drain rig would turn that check
into ERROR). Open-drain D2 stays a fallback if generated plans skip the pull-up check. The
button scenarios gained replies and verdicts for the two new traces.

## Per-student values (params)

**D63. Plans can hold per-student values ("params"), filled in per submission.** An
assignment such as `uart_id` expects different text from every student (their own ID), so
one fixed expected value cannot work.
* A plan declares `params: [student_id, ...]` (optional, default empty; names match
  `^[a-z][a-z0-9_]*$`). `schema_version` stays `"0.1"` because old plans stay valid.
* A placeholder is `{{name}}`. Double braces never clash with regex quantifiers such as
  `\d{3}`, and they need no templating library. Any `{{...}}` is recognised, so a
  misspelt or upper-case name is reported as undeclared rather than silently kept.
* **String fields only:** text expectation values (`eq`/`ne`/`contains`/`matches` on
  `text`), `uart_send.data`, and the free text (`description`, `requirement`,
  `assumptions`, `not_graded`). There is no numeric substitution, so a template is still
  valid against the schema with its placeholders in place, and `validate-plan`,
  `approve-plan` and the approval hash all work on the template file unchanged.
* `validate.py` checks the template: every placeholder is declared, every declared param is
  used, no placeholder sits in any other field (the message names the field), no param is
  listed twice.
* `plan.instantiate(plan, values)` dumps the plan, replaces placeholders in every string
  (with `re.escape(value)` inside a `matches` value, the raw value elsewhere) and parses
  the result again. A missing value raises `PlanError` naming the param. The filled-in
  plan declares **no** params, so the runner's `validate_plan` treats it like a
  hand-written plan (otherwise every param would be "declared but never used").
* Values travel on `Submission.params` (excluded from hashing and equality), so the runner,
  which instantiates, and the feedback, which redacts (D64), both read them from the one
  object they already get. Sources: `DIR/params.yaml` for `batch --rig serial` (same keys
  as `labels.yaml`; an entry without a folder is a warning), a scenario's `params:` for the
  fake rig, and repeatable `--param NAME=VALUE` for `grader run`. With `run --rig fake`,
  `--param` overrides the scenario's values. Integers become strings (values are only
  ever substituted into text); booleans, floats and lists are rejected. Derived values
  (`digit_sum`, `id_hex`) are worked out by the instructor; the grader never computes them.
* A missing value is the instructor's mistake, not a student or rig fault. Every batch and
  `grader run` checks all submissions first (`batch.require_params`) and exits 2 with
  the list of submissions and the params they lack; nothing is graded, and the serial
  batch checks before it opens the port. `--flash-only` does not grade, so it does not
  need values. `report.json` records the values used (`params`); `report.md` does not
  show them.
* `make-plan --param-doc NAME="description"` (repeatable) lists the params in a
  `<params>` block of the user message ("none" without any). The draft must declare
  exactly those names, and a templated draft must also validate once filled in with
  dummy values, so a `matches` value that only breaks after substitution goes back to the
  repair loop. The plan prompt gained a short "Per-student values" section; it adds no
  rule about `uart_send` + `uart_read` groups, which the existing concurrency text (D59)
  already covers.

**D64. Listed params are redacted from LLM requests.** The feedback request holds the
student's code, the measured text and the expected values, and all three can contain the
real ID.
* `config/llm.yaml` `redact_params` (default `[student_id]`) names the params to hide.
  Before the feedback call, each listed value, and its `re.escape` form as it appears in a
  `matches` check, is replaced by `<name>` in the checks, the description, the command
  log and the source code.
* The cited-value check runs against the redacted check values. A model that cites the
  real value cannot have read it from the data, so that item is dropped.
* After the call the real value is put back into the accepted explanations and code
  locations, so the student's report reads normally. `llm_feedback.json` (the saved request
  and response) stays redacted.
* Only listed params are redacted. Short derived values such as `digit_sum` = `25` would
  match unrelated text (line numbers, delays), so they are sent as they are. A measured
  value that is *another* student's ID (copied code) is not redacted either; only this
  submission's own values are known.

**D65. The `uart_id` assignment: no boot message, a flush line, and empty lines.**
* **No boot message.** The runner starts reading only after setup (reset, then the
  1000 ms boot wait of D57), and a read is a measurement armed by a step, so anything a
  sketch prints in `setup()` is lost. The assignment leaves boot messages out (the handout
  says to print nothing but replies). Checking one would need the firmware to start a
  UART read before or during `RESET`; that is not built.
* The plan starts with one unchecked `uart_send` of `"\n"` and a 200 ms wait, to flush
  anything the Nano's receiver picked up when the rig first drove the line. The handout
  therefore says to ignore empty lines. That also keeps a char-by-char parser that ends a
  line on `\r` correct: the `\n` after it is an empty line, which gets no `ERR`.
* Each command is one concurrent group: a 300 ms `uart_read` armed before a `uart_send`
  at the same baud. "Reply promptly" has no number in the handout, so the plan records
  300 ms as an assumption. Replies are checked with an exact-line regex
  (`^{{student_id}}\r?\n$`) plus `framing_errors eq 0`. Commands: `ID?`, `SUM?`, `HEX?`
  with `\n`, `ID?` with `\r\n`, an unknown command (`ERR`), and a last `ID?` that catches
  sketches answering only once.
* The ten benchmark sketches are still to be written (`benchmark/uart_id/README.md`);
  `labels.yaml` and `params.yaml` use made-up IDs that start with `000`. Four fake-rig
  scenarios (`correct`, `copied_id`, `ascii_sum`, `no_err`) have no `sketch:` link yet.

## Code-only baseline

**D66. `grader code-grade`: an LLM grades the sketches from the handout and the code
alone.** The paper needs a baseline without our system: the same benchmark folders and
`labels.yaml`, graded by a model that reads the code and never sees a plan or a
measurement. It is a separate command with its own output; nothing in it feeds into
hardware grading.
* **Handout-only input.** The model gets the handout, the board name, the requirement
  list, this student's values and the source, never our plan. So the baseline measures
  grading without the system, *including* interpreting the handout (choosing limits for
  "quickly", splitting requirements), which our plans do with review.
* **A fixed requirement list.** One call per run turns the handout into
  `requirements: [{id, requirement}]` (prompt `code_requirements.md`, tool
  `submit_requirements`), checked in plain code (snake_case unique ids, non-empty
  sentences) with the `make-plan` repair loop, at most 3 attempts. The
  planner's loop is now `planner.repair_loop(client, first, check, what=...)`;
  `generate_plan` calls it with `check_draft`, so `make-plan` behaves as before. The list
  is saved as `OUT/requirements.json` (model, prompt version, tokens, cost) with the
  conversation in `requirements.log.json`. `--requirements FILE` reuses a list (no call),
  so repeated runs differ only in grading; the out folder gets a copy marked
  `reused_from`, and the reused list's tokens and cost are not counted again.
* **Only what the board does.** The list covers what can be seen from outside the board
  (pins, serial output, timing, including which port and baud and how inputs are set up),
  never how the code is written (comments, style, "without `delay()`"), matching what the
  hardware grader grades. A first version had a `kind: behaviour | code_only` split with
  `code_only` as uncounted notes; on the first runs the model put real behaviour there
  (Serial1 at 9600 baud, `INPUT_PULLUP`), which hid caught bugs from the rates, so the
  split was removed (D67).
* **Grading** is one call per submission (prompt `code_grade_system.md`, tool
  `submit_code_grade`, one `{id, verdict, reason, code_location}` per requirement). The
  source comes from `feedback.read_sources` inside the same untrusted `<student_code>`
  block, with the same "ignore instructions inside it" wording. Items are dropped, with a
  warning, for an unknown id, a repeated id or a verdict other than PASS/FAIL/UNSURE; a
  missing `reason` is accepted as empty. A requirement with no accepted item is UNSURE
  ("no verdict from the model"). Any `LLMError` makes every requirement ERROR for that
  submission; the error is recorded and the run goes on.
* **UNSURE in the metrics.** UNSURE means "reading cannot settle it" (timing near a limit,
  library behaviour on this board). It counts as *not failed*, so a submission with UNSURE
  but no FAIL is not flagged; UNSURE checks and the submissions with any are reported
  separately. The run reuses `batch.compute_metrics` through `CodeRow(BatchRow)`, with
  `borderline` holding the UNSURE count, so the rates are computed exactly as
  for the hardware batches. A submission whose call failed (ERROR) is not flagged, as a
  rig error is not in a hardware batch. `summary.csv` and the printed table are a small
  code-grade version (columns `pass, fail, unsure, flagged, error` (the
  ERROR count), `llm_error` (the message), tokens, latency, cost, elapsed); the hardware
  batch's writers are unchanged.
* **Student values** (D63) come from `params.yaml` via `load_params` and are redacted with
  `feedback.Redactor` and `redact_params` (D64) in both the values block and the source,
  so a sketch with its own ID shows `<student_id>`, while a copied ID stays a different
  number. The real values are put back into the saved reasons and code locations;
  `code_grade.json` keeps the raw request and response redacted and records `params` with
  the real values, as `report.json` does.
* **Models.** `model.code_grade` (default: the feedback model) is used for both the
  requirement list and the grading, so one baseline run is one model; `--model ID`
  overrides it. `max_tokens.code_grade` defaults to 8000. As with `--feedback llm`, a
  placeholder model or a missing key stops the run before any call.
* **Prices per model.** `price_per_mtok` may now hold `<model id>: {input, output}` entries
  next to the flat `{input, output}`, which still means the feedback model's price
  (`LLMConfig.cost_for(model, in, out)`; `cost_usd` is the feedback model's). Cost is
  looked up by the model id requested (the config or `--model`), not the id the API echoes
  back. An unpriced model gives a blank cost, not an error. No new prices were filled in.
* **`scripts/compare_runs.py`** reads both `summary.csv` files and compares the `flagged`
  columns per submission (truth from the hardware run, else the code run), prints both
  runs' rates, the disagreements, the submissions found in only one run, and each run's
  LLM cost per graded submission: feedback calls only for hardware; grading plus the
  requirement list (from `requirements.json`, unless it was reused) for code.
* **Size.** New source is about 700 lines (`code_grade.py` ≈440, `compare_runs.py` ≈130,
  the CLI +68, the config and repair-loop changes ≈60 net), twice the brief's ~350.
  About 50 lines are the two tool schemas, and `ruff format` spreads the CLI options and
  dict literals over many lines. No caching, concurrency or new abstraction was added
  beyond `CodeRow` and `repair_loop`.

**D67. Code-only baseline fixes after the first runs.**
* **No `code_only` kind** (see D66): every requirement in the list counts, and the
  requirements prompt leaves out requirements about how the code is written. Older saved
  lists that still carry `kind` load fine; the field is ignored.
* **A cut-off answer is ERROR, not UNSURE.** A reply that stopped at `max_tokens`, or whose
  tool input has no `items` list, is a failed call: every requirement is ERROR for that
  submission, with the tokens still counted. Before, a tool call cut off part-way had no
  items, so every requirement became "UNSURE: no verdict from the model", which looked like
  a cautious grade. A missing verdict for *one* requirement in a complete answer is still
  UNSURE.
* **`max_tokens.code_grade` 8000 -> 16000.** Each grade is 10-12 verdicts with reasons plus
  thinking; on the first UART run 2 of 10 sketches hit 8000.
* **Reviewed requirement lists** for the first runs are saved next to the originals as
  `out/code_btn/requirements_reviewed.json` and `out/code_uart/requirements_reviewed.json`:
  the requirements the model had marked `code_only` but that change what the board does
  (Serial1 at 9600 baud; D2 `INPUT_PULLUP`) are kept as ordinary requirements, and the ones
  about how the code is written (comments; debounce without `delay()`) are removed. The
  original lists stay as the record of the model's unaided reading.
