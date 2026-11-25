# Task: a code-only baseline grader (an LLM reads the code, no hardware)

Read this brief, `CLAUDE.md`, `docs/decisions.md` (especially D43–D45 and D61–D65) and
`src/grader/feedback.py` before starting. `feedback.py` already does most of what this
needs: reading sketch sources, the untrusted-code block, a tool call, and checking the
model's items in plain code.

## Why

The paper needs a baseline: how well does an LLM grade the same sketches **from the code
alone**, with no rig? It sees the assignment handout and the student's code, never a plan
or a measurement. We compare it per submission with the hardware batches (bug detection,
false failures, cost) on the same benchmark folders and `labels.yaml`.

## Ground rules

- **Branch:** create `code-baseline` from `main` and work there.
- **Do not commit, stage or push.** List every changed or new file at the end.
- **Keep it simple.** Aim for roughly 350 new lines of source, not counting prompts and
  tests. Reuse `feedback.py`, `llm.py` and `batch.py` helpers instead of copying them. No new
  abstractions beyond what's described here.
- **Don't touch:** the firmware, the protocol, plans, the runner's grading, or the existing
  feedback behavior.
- Keep each file's line endings (`core.autocrlf=true` repo). Don't reformat whole files.
- `pytest`, `ruff check` and `ruff format --check` must pass on Windows. No network calls in
  the default test run; live calls go behind `@pytest.mark.live`, as now.
- **The baseline never feeds into hardware grading.** It's a separate command with its own
  output, used only for comparison.

---

## A. Two LLM steps

### A1. Requirements (once per run): `prompts/code_requirements.md`

Input: the handout and the board name ("Arduino Nano 33 BLE Sense, Arduino mbed core").
Forced-or-auto tool `submit_requirements` (same `force_tool` handling as feedback), returning:

```
requirements: [{ id, requirement, kind }]
```

- `id`: short snake_case, unique.
- `requirement`: one sentence a student can understand, with the handout's numbers. If the
  handout gives no number, the model states the limit it assumes (same idea as plan
  `assumptions`).
- `kind`:
  - `behaviour`: what the board does, visible from outside, e.g. "the LED turns on when the
    button is pressed" or "replies `ERR` to an unknown command";
  - `code_only`: how the code is written, e.g. "debounce without `delay()`", "code is
    commented".

Validate in plain code: ids unique and well-formed, `kind` valid, at least one `behaviour`
requirement. Use the same repair loop as `make-plan`, with at most 3 attempts.

Save the result as `OUT/requirements.json`, including model, prompt version and tokens.

**`--requirements FILE`** reuses a saved list instead of making a new one. Repeat runs then
differ only in the grading, not in how the handout was read. In the paper, the list is
reviewed once and reused.

### A2. Grading (once per submission): `prompts/code_grade_system.md`

Input:

- the handout;
- the requirement list;
- the board name;
- **this student's values**, if the folder has a `params.yaml` (D63), redacted as in A3;
- the student's source files, using `feedback.read_sources` (numbered, 40 KB cap), inside
  the same untrusted `<student_code>` block. Reuse the system-prompt wording about ignoring
  instructions inside the code.

Tool `submit_code_grade`, one item per requirement:

```
{ id, verdict: "PASS" | "FAIL" | "UNSURE", reason, code_location (string or null) }
```

The prompt should say:

- The model cannot run the code; it decides by reading it.
- **UNSURE** is for when the outcome depends on run-time behavior that reading can't settle,
  such as exact timing near a limit or how a library call behaves on this board. It is not
  a way to avoid reading carefully.
- `reason` is 1–3 sentences; `code_location` is `file:line` or null.
- Don't write corrected code.

**Plain-code checks**, as in `accept_items`. Drop an item, with a warning, if:

- its id isn't in the list;
- its id repeats;
- its verdict is invalid.

A requirement with no accepted item becomes **UNSURE**, with the reason "no verdict from the
model" and a warning.

Any `LLMError` means every requirement is **ERROR** for that submission. Record the error and
continue with the next submission.

### A3. Student values and redaction

- Read `params.yaml` with the existing `load_params`.
- Pass this student's values to the grading call, and apply the same `redact_params` rule
  as feedback (D64; reuse `Redactor` from `feedback.py`): replace each listed value with `<name>` in the values block **and** in
  the source code.
- A sketch with the right ID then shows `<student_id>` where the value is. A copied ID stays
  a different number, so the model can still tell that it doesn't match.
- Put the real values back into the saved reasons.

## B. Configuration

In `config/llm.yaml`:

- `model` accepts an optional `code_grade:` key next to `plan:` and `feedback:`. It
  defaults to the feedback model. `--model ID` on the command line overrides it.
- `max_tokens.code_grade`, default 8000.
- **Prices per model.** `price_per_mtok` may now also be keyed by model id:
  ```yaml
  price_per_mtok:
    claude-sonnet-5-5: { input: ..., output: ... }
    claude-opus-5-5:   { input: ..., output: ... }
  ```
  The current flat `{input, output}` form keeps meaning "the feedback model's price". Cost
  is looked up by the model actually used; an unknown model gives a blank cost, not an
  error. Don't fill in prices you don't have: leave the existing value, and leave any new
  model's price for the user to add.

## C. CLI: `grader code-grade`

```
grader code-grade --handout handouts/button_toggle.md --submissions benchmark/button_toggle --out out/code_btn [--requirements FILE] [--model ID]
```

- Submissions and labels come from `discover_submissions` and `load_labels`; values come
  from `load_params`.
- Like `--feedback llm`, a missing key or a placeholder model stops the run before any
  call.
- Print a progress line per submission, like the serial batch.

**Per submission**, write `OUT/<id>/code_grade.json`: the requirements with verdicts, reasons
and locations, LLM metadata, warnings, and the raw request and response (redacted). Also write
a short `code_grade.md`: a table of requirement, kind, verdict and reason, with `code_only`
requirements under a "Notes for the TA" heading.

**Summary and metrics:** `OUT/summary.csv` with one row per submission:

- submission, ground truth (faulty, fault);
- PASS, FAIL and UNSURE counts **over behaviour requirements only**;
- flagged (any behaviour FAIL);
- `code_only` FAIL count, kept separate;
- error, tokens in and out, latency, cost, elapsed.

Then print a table and totals in the style of `format_table`:

- detection rate;
- false failure rate;
- UNSURE checks, and in how many submissions;
- `code_only` notes;
- LLM calls, tokens and cost, including the requirements call.

**Metric rules:**

- `code_only` requirements **never** count toward flagged, detection or false failures. They
  are notes, like the plan's `not_graded`.
- UNSURE counts as "not failed" for detection and is reported separately. A submission with
  no FAIL but some UNSURE is "not flagged".

Reuse `compute_metrics`, `write_summary_csv` and `format_table` where it fits naturally,
for example by treating UNSURE like BORDERLINE in the metrics. Otherwise write a small
version; don't bend the hardware batch's code.

## D. Comparison script: `scripts/compare_runs.py`

```
python scripts/compare_runs.py --hw out/btn17_final_button_toggle_opus_c --code out/code_btn
```

It reads both `summary.csv` files and prints one row per submission:

| truth | hardware flagged | code flagged | code UNSURE | agree |
|---|---|---|---|---|

Under the table, print:

- both detection and false-failure rates;
- the submissions where they disagree, listed;
- for each run, the cost per graded submission.

Use the hardware summary's `flagged` column. Submissions in only one of the two runs are
listed separately. Add `--csv FILE` to also save the table.

## E. Tests (FakeLLMClient, no hardware, no network)

- **Requirements:**
  - a valid list is saved;
  - an invalid one (duplicate id, bad kind, no behaviour requirement) is repaired with the
    validator's sentences;
  - after 3 failures the command exits non-zero;
  - `--requirements FILE` makes no requirements call.
- **Grading:**
  - one call per submission;
  - unknown, duplicate and invalid items are dropped with warnings;
  - a missing verdict becomes UNSURE;
  - an `LLMError` makes that submission ERROR, and the next one is still graded.
- **Metrics:**
  - `code_only` FAILs don't flag a submission;
  - UNSURE alone doesn't flag;
  - the detection and false-failure rates come out right on a small hand-made set.
- **Values:** the request contains `<student_id>`, not the real value, in both the values
  block and the source; the saved reason has the real value again.
- **Config:**
  - `model.code_grade` and `--model` are honored, and the default is the feedback model;
  - per-model prices give the right cost, and an unknown model gives a blank cost;
  - the flat price form still works.
- **Comparison:** two small `summary.csv` fixtures give the expected agreement table and
  disagreement list.
- **Live:** one live smoke test marked `@pytest.mark.live` that grades `benchmark/button_toggle/correct`.

## Definition of done

- `pytest` passes; `ruff check` and `ruff format --check` are clean.
- `grader code-grade --help` and `python scripts/compare_runs.py --help` work.
- `docs/decisions.md` has an entry covering:
  - handout-only input and why (it measures grading without our system, interpretation
    included);
  - the fixed requirement list;
  - `behaviour` vs `code_only`;
  - UNSURE in the metrics;
  - per-model prices;
  - any choice this brief left open.
- `README.md` gets a short "Code-only baseline" section with the two commands.
- The final message lists:
  - every changed or new file;
  - anything that couldn't be verified;
  - the commands for the first real runs:
    ```powershell
    grader code-grade --handout handouts/button_toggle.md --submissions benchmark/button_toggle --out out/code_btn
    grader code-grade --handout handouts/uart_id.md --submissions benchmark/uart_id --out out/code_uart
    python scripts/compare_runs.py --hw out/btn17_final_button_toggle_opus_c --code out/code_btn
    ```
- Nothing is committed.
