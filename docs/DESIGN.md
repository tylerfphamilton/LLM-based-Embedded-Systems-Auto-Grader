# Design (host software, v0.1)

## Data flow

```
plan.json ──load──▶ Plan ──validate(pinmap)──▶ errors[] (abort) │ ok
                                                                ▼
submission ──Flasher.flash()──▶ FlashResult        Runner (one submission)
                                                     │ for each step:
                                                     │   step ─▶ Command ─to_line()─▶ "FREQ D5 100"
                                                     │                                  │ Transport.send_line
                                                     │   Measurement ◀─parse_response── "OK frequency_hz=1000.2 …"
                                                     │       │                          (Fake: FakeDevice / Serial: STM32)
                                                     │       ▼
                                                     │   compare(expectation, measurement, RigProfile) ─▶ Verdict
                                                     │   FAIL ─▶ FeedbackGenerator.explain()  (NullFeedback for now)
                                                     ▼
                                       Report ──▶ report.json + report.md
batch: many scenarios ─▶ many Reports + ground truth ─▶ summary.csv + metrics
```

The FakeRig sits *below* the protocol layer: it receives the exact text lines the real
firmware would and answers with the same text format, so serialization and parsing are
exercised by every test.

## Modules

| Module | Key items | Responsibility |
|---|---|---|
| `plan.py` | `Plan`, `Step` (union on `op`), `MeasureStep` (union on `primitive`), `Expectation` (union on `op`), `PRIMITIVE_FIELDS`, `load_plan`, `export_schema` | Test-plan schema (pydantic v2, `extra="forbid"`), JSON Schema export |
| `pinmap.py` | `PinMap`, `PinInfo`, `load_pinmap` | Student pin name → STM32 pin + capabilities |
| `validate.py` | `validate_plan(plan, pinmap) -> list[str]` | Semantic checks the schema cannot express; one sentence per error |
| `protocol.py` | `Command` subclasses, `to_line()`, `parse_command()`, `Ok`/`Err`, `parse_response()`, `encode_ok()`, `command_for_step()` | The text protocol, both directions |
| `transport.py` | `Transport` ABC, `FakeTransport`, `SerialTransport`, `find_port()` | Moving lines; nothing else |
| `fake_rig.py` | `Scenario`, `load_scenario`, `FakeDevice` | Simulated measuring board for one simulated submission |
| `rig_profile.py` | `RigProfile`, `load_rig_profile` | Known measurement error per field, timeouts |
| `compare.py` | `Measurement`, `compare()` → `Outcome` | Deterministic expectation → verdict, incl. BORDERLINE zone |
| `runner.py` | `run()`, `RigClient`, `Clock`/`FakeClock` | Executes a plan for one submission |
| `report.py` | `Report`, `CheckResult`, `Verdict`, `write_reports()` | JSON + Markdown output |
| `flasher.py` | `Flasher` ABC, `NoopFlasher`, `ArduinoCliFlasher`, `Submission` | Getting the student's code onto the board |
| `feedback.py` | `FeedbackGenerator` protocol, `NullFeedback` | Hook for LLM feedback later |
| `batch.py` | `run_batch()`, `BatchMetrics` | Many scenarios + benchmark metrics |
| `cli.py` | `grader export-schema / validate-plan / run / batch` | Typer CLI |

## Key rules (from the brief)

1. Plans are data. No module branches on the assignment name.
2. Verdicts are pure functions of (expectation, measurement, rig profile).
3. Rig faults (`ERR …`, timeout, malformed line, missing field) → `ERROR`, never `FAIL`.
   A *valid* "no signal" measurement (`null`) → `FAIL`.
4. All signal timing happens on the measuring board, including waits (`WAIT <ms>`).

Concurrency: a `measure` step with `concurrent_with_next: true` is sent as
`ARM <cmd>`; consecutive armed measures are followed by one stimulus step, then
`COLLECT <slot>` for each. See `docs/decisions.md` (D3).
