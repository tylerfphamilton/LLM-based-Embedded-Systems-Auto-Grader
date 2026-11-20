# Task: a UART "student ID" assignment, with per-student values in plans

Read this brief, `CLAUDE.md`, `docs/protocol.md` and `docs/decisions.md` (D57–D61) before
starting.

## Ground rules

- **Branch:** create `uart-id` from `main` and work there.
- **Do not commit, stage or push.** List every changed or new file at the end.
- **Keep it simple.** Aim for roughly 250 new lines of source, not counting tests, sketches,
  plans, handouts and scenarios. No expression language, no templating library, no new
  abstractions beyond what's described here.
- **Don't touch:** the firmware, the protocol, the existing plans, scenario replies or
  `expected_verdicts`.
- Keep each file's line endings (`core.autocrlf=true` repo). Don't reformat whole files.
- `pytest`, `ruff check` and `ruff format --check` must pass on Windows. No network calls
  in the default test run.
- **No rig is attached.** Don't run anything that needs the STM32. If `arduino-cli` and the
  `arduino:mbed_nano` core are installed, compile the sketches (section F); don't upload.

---

## The assignment (for context)

Each student's sketch answers commands on **Serial1 at 9600 baud** with values derived from
**their own** university ID. Every student's correct output is different, so a plan can't
hold one fixed expected value. The grader fills in each student's values from a roster.

Commands (one per line; the sketch must accept both `\n` and `\r\n` endings):

| Command | Reply (one line, ending `\r\n` or `\n`) |
|---|---|
| `ID?` | the 9-digit ID, e.g. `905123456` |
| `SUM?` | the sum of its digits, e.g. `35` |
| `HEX?` | the ID as an upper-case hex number without leading zeros, e.g. `35F31680` |
| anything else | `ERR` |

**No boot message.** The runner can only start a serial read after setup (reset + boot
wait), so anything printed during boot is lost. Leave it out of the assignment and record
this limitation in `docs/decisions.md`. Don't build a workaround.

## A. Per-student values ("params")

### A1. Roster: `params.yaml`

Next to `labels.yaml` in a submissions folder, with the same keys (submission ids):

```yaml
# benchmark/uart_id/params.yaml: per-student values. Made-up IDs only.
submission_01: { student_id: "000412387", digit_sum: 25, id_hex: "64AE3" }
```

- Values are strings or integers. Store them as strings internally (an integer `35` becomes
  `"35"`), because they are only ever substituted into text.
- Derived values (`digit_sum`, `id_hex`) are worked out in advance by the instructor. The
  grader never computes them.
- Load with `load_params(folder) -> dict[str, dict[str, str]]` in `batch.py`, next to
  `load_labels`. A missing file means no params; an entry for a missing folder is a warning,
  as in `load_labels`.

### A2. Plans declare and use params

- Add an optional top-level field to `Plan`: `params: list[str]` (default empty), each
  matching `^[a-z][a-z0-9_]*$`. Keep `schema_version` at `"0.1"` (the field is optional and
  old plans stay valid). Regenerate `schemas/plan.schema.json` (`grader export-schema`).
- A placeholder is `{{name}}`. Double braces so it never clashes with regex quantifiers such
  as `\d{3}`.
- **Placeholders are only allowed inside string fields:** expectation `value`s of text ops
  (`eq`/`ne`/`contains`/`matches` on a text field), `uart_send.data`, and the free-text fields
  (`description`, `requirement`, `assumptions`, `not_graded`). No numeric substitution.
  This keeps the plan valid against the schema with its placeholders in place.

### A3. Validation (`validate.py`)

On the template (placeholders still in place):

- every `{{name}}` used must be in `params`, and every declared param must be used at least once;
- a placeholder outside an allowed field is an error naming the field;
- one sentence per error, as now (they go back to the LLM in `make-plan`'s repair loop).

### A4. Filling in values: `instantiate(plan, values) -> Plan`

In `plan.py`:

- dump the plan, replace placeholders in every string, then `parse_plan` the result;
- inside a `matches` expectation, substitute `re.escape(value)`; everywhere else, the raw value;
- a missing value raises `PlanError` naming the param.

Call `validate_plan` on the instantiated plan too (the runner already does).

### A5. Where values come from

| Command | Source |
|---|---|
| `grader batch --rig serial --submissions DIR` | `DIR/params.yaml` |
| `grader batch --rig fake --scenarios DIR` | an optional `params:` field in each scenario YAML |
| `grader run` | repeatable `--param name=value` |

- **Before grading starts,** check that every submission has a value for every declared
  param. If any don't, print which submissions lack which params and exit 2. A missing value
  is the instructor's mistake, not a student fault or a rig fault.
- A plan without `params` behaves exactly as today.
- `report.json` records the values used (`params`); `report.md` doesn't need to show them.
- `approve-plan` and the approval check work on the template file, unchanged.

### A6. `make-plan`

- New repeatable option `--param-doc NAME="description"`, for example
  `--param-doc student_id="the student's 9-digit ID"`. These become the plan's `params`.
- The user message lists the available params with their descriptions, or says "none".
- Add a short **"Per-student values"** section to `prompts/plan_system.md`: use `{{name}}`
  only for the listed params, only inside text values and `uart_send.data`, and set `params`
  to exactly the listed names. Keep it to a few lines.
- **Before writing the prompt section,** check `plan_system.md` and `validate.py` for how
  `uart_send` + `uart_read` groups already work (D59: same baud, one stimulus per group), so
  the section doesn't repeat or contradict them.

### A7. Keep student IDs out of LLM requests

The feedback request contains the student's code, the measured text and the expected values,
and all of them can contain the real ID.

- New `config/llm.yaml` key `redact_params: [student_id]` (default: that list).
- Before the feedback call, replace each listed param's value with `<name>` everywhere in the
  request text (source code, checks, command log).
- Run the cited-value check against the **redacted** check values.
- After the call, put the real values back into the accepted explanations and code
  locations, so the student's report reads normally.
- `llm_feedback.json` (the saved request and response) stays redacted.
- Only listed params are redacted. Short derived values like `digit_sum` would match
  unrelated text, so they are not redacted by default.

## B. Mock handout: `handouts/uart_id.md`

Write it like a course handout, in the style of `handouts/button_toggle.md`:

- the commands table above;
- 9600 baud, Serial1 (not USB `Serial`);
- "use your own university ID";
- "reply promptly" **without** a number, so the plan has to record an assumption;
- accept both line endings.

Mark it as a mock handout for testing, like the others.

## C. Hand-written plan: `plans/uart_id.json`

- `params: ["student_id", "digit_sum", "id_hex"]`, `setup.boot_wait_ms: 1000` (D57 rig timing).
- **One concurrent group per command.** A `uart_read` (window long enough for a reply, e.g.
  300 ms) with `concurrent_with_next: true`, then a `uart_send` at the same baud. Check the
  reply with `matches` against an exact line, for example `^{{student_id}}\r?\n$`, plus
  `framing_errors eq 0`.
- **Cover:**
  - `ID?`, `SUM?` and `HEX?`, each with `\n`;
  - `ID?` again with `\r\n`;
  - an unknown command → `ERR`;
  - a second `ID?` at the end, so "only answers once" sketches fail.
- **Start with one `uart_send` of `"\n"`** before the first real command, with no check, to
  flush anything the Nano's receiver picked up when the line was first driven. Record it as
  an assumption.
- Add it to the existing test that every example plan validates, and update that test to
  instantiate templated plans with dummy values. Validating the template alone isn't enough,
  because `matches` values must still compile after substitution.

## D. Benchmark folder: `benchmark/uart_id/`

**Don't write the sketches.** The user writes them. Create:

- `labels.yaml` and `params.yaml` covering the planned submissions below, with **made-up**
  9-digit IDs starting `000` (clearly fake) and their derived values worked out correctly.
  The `copied_id` entry needs a value for a *different* ID than the one its sketch will
  print; note that in a YAML comment.
- A short `README.md` listing each planned submission and the bug it should contain, so the
  user can write the sketches to match:

| Submission | Faulty | Bug |
|---|---|---|
| `correct` | no | — |
| `correct_alt_style` | no | different parsing style (e.g. char-by-char state machine) |
| `copied_id` | yes | prints another student's ID |
| `ascii_sum` | yes | sums the characters' ASCII codes, not the digit values |
| `lf_only` | yes | only accepts `\n`; with `\r\n` the `\r` breaks the match |
| `no_err` | yes | ignores unknown commands instead of replying `ERR` |
| `answers_once` | yes | stops replying after the first command |
| `wrong_baud` | yes | `Serial1.begin(115200)` |
| `hex_lowercase` | yes | prints hex in lower case |
| `usb_serial` | yes | uses `Serial` instead of `Serial1` |

## E. Fake-rig scenarios: `scenarios/uart_id/`

- Add scenarios for `correct`, `copied_id`, `ascii_sum` and `no_err`, each with `params:`,
  `ground_truth` and `expected_verdicts`.
- Replies are literal text with that scenario's values filled in. Don't add placeholders to
  scenario replies.
- Don't add `sketch:` links: the sketches don't exist yet, and `test_scenario_sketch_links_exist`
  would fail. Say in the README that the links come with the sketches.
- `grader batch --rig fake --scenarios scenarios/uart_id --plan plans/uart_id.json` must
  give the expected verdicts.

## F. Tests (no hardware, no network)

- **Params loading:** `params.yaml` loads; integers become strings; a missing file means no
  params; an unknown key gives a warning.
- **Validation:**
  - an undeclared placeholder is an error;
  - a declared but unused param is an error;
  - a placeholder in a non-string field (or outside the allowed fields) is an error;
  - a plan without params is unchanged.
- **`instantiate`:**
  - fills in text expectations and `uart_send.data`;
  - `re.escape` is applied in `matches` (test a value with `.` or `+`);
  - a missing value raises `PlanError` naming the param.
- **Batch:**
  - a submission missing a param stops the batch before grading (exit 2) with the list of
    missing values;
  - the fake batch for `scenarios/uart_id` gives the expected verdicts.
- **`grader run --param`:** works; a malformed `--param` (no `=`) exits 2.
- **`make-plan`:** `--param-doc` appears in the user message and in the plan's expected
  `params`. Use `FakeLLMClient` and `--dry-run`.
- **Redaction:**
  - the feedback request contains no listed param value;
  - the explanations in the report contain the real value again;
  - cited values are checked against the redacted text.
- **Unchanged behavior:** the pwm, button and blink fake batch metrics are unchanged.

## Definition of done

- `pytest` passes; `ruff check` and `ruff format --check` are clean;
  `grader export-schema --check` passes.
- `grader validate-plan plans/uart_id.json` passes, and the fake `uart_id` batch gives the
  expected verdicts.
- `grader make-plan --handout handouts/uart_id.md --name uart_id_llm --param-doc ... --dry-run`
  prints a sensible request listing the params.
- `docs/decisions.md` has entries for:
  - params;
  - the `{{name}}` syntax and why;
  - string-only substitution;
  - redaction;
  - the no-boot-message limitation;
  - any choice this brief left open.
- `README.md` gets a few lines on `params.yaml`, `--param` and `--param-doc`. `CLAUDE.md`
  gets the new rules (placeholders only in strings; missing values stop the batch; listed
  params are redacted before LLM calls).
- The final message lists:
  - every changed or new file;
  - anything that couldn't be verified;
  - the commands to run once the sketches exist:
    ```powershell
    grader batch --plan plans/uart_id.json --submissions benchmark/uart_id --rig serial --out out/uart_id_hw --feedback none
    grader make-plan --handout handouts/uart_id.md --name uart_id_llm --param-doc student_id="the student's 9-digit ID" --param-doc digit_sum="sum of the ID's digits" --param-doc id_hex="the ID as upper-case hex"
    ```
- Nothing is committed.
