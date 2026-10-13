# CLAUDE.md

Host software for an embedded-systems autograder (UCLA M202A). Python 3.11+, src layout,
pydantic v2, typer, pytest, ruff. Read `docs/DESIGN.md` first, then `docs/decisions.md`.

## Non-negotiable rules

1. **The test plan is data, not code.** Never add assignment-specific logic (no
   `if assignment == "pwm"`, no per-assignment field names in Python). A new assignment
   must need only `plans/<name>.json` + `scenarios/<name>/*.yaml`.
2. **Verdicts are deterministic.** `compare.compare()` is a pure function of
   (expectation, measurement, rig profile). No randomness, time or I/O in verdict code.
   Every RNG is seeded explicitly (only the FakeRig uses one).
3. **Rig faults are not student faults.** ERR replies, timeouts, malformed lines and
   missing fields → `ERROR`, never `FAIL`. A valid "no signal" (`null`) → `FAIL`.
4. **All timing happens on the measuring board.** The host never sleeps or times signals
   (waits are `WAIT <ms>` commands). Inject a clock; tests never sleep.
5. The FakeRig sits **below** the protocol layer: it receives and sends real protocol text.
   Don't shortcut it by passing Python objects.
6. No LLM or network calls in this repo yet; use the `FeedbackGenerator` hook. Nothing
   from feedback may influence a verdict.
7. No global state. Use `pathlib`; never hardcode serial port names (find by USB VID).

## Commands

```bash
pip install -e ".[dev]"
pytest                         # whole suite must stay < 5 s, no hardware/network
ruff check . && ruff format .
grader export-schema           # after ANY change to plan.py; test_committed_schema_is_fresh enforces it
grader batch --plan plans/pwm_1khz.json --scenarios scenarios/pwm/ --out out/pwm
```

On Windows use `.venv\Scripts\grader` / `.venv\Scripts\python -m pytest` if the venv is
not activated.

## Conventions

* Change the wire protocol → update `docs/protocol.md` **and** the round-trip tests in
  `tests/test_protocol.py` (`test_every_command_class_is_covered` will catch new classes).
* New open design choice → add an entry to `docs/decisions.md`.
* New scenario → include `ground_truth` and `expected_verdicts`; the end-to-end tests run
  every `scenarios/*/*.yaml` against `plans/<assignment>.json`.
* Validation messages are full sentences naming the step: `step 'freq': pin D7 is not in
  the pin map.`
* Hardware paths (`SerialTransport`, `ArduinoCliFlasher`) are untested on real boards;
  test them only with injected fakes (`serial_factory`, `port_lister`, `run`).
