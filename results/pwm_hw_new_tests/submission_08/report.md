# Autograder report: pwm_1khz_llm_v2

**Submission:** `submission_08`  
**Result: 0 of 3 checks passed** · 3 failed · 0 borderline · 0 could not be measured

> Verify that the student's Nano 33 BLE Sense generates a free-running 1 kHz, 25% duty cycle square wave on D5 immediately after reset, without any stimulus.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. | `frequency_hz` | ≈ 1000 Hz ± 2% | no value (null) | ❌ FAIL |
| The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. | `duty_pct` | ≈ 25% ± 1 pt | no value (null) | ❌ FAIL |
| The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. | `edge_count` | ≥ 2 | 0 | ❌ FAIL |

## What to fix

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`frequency_hz`)

- **Why:** nothing was measured for 'frequency\_hz' (null, e.g. no signal or no response); expected ≈ 1000 Hz ± 2%
- **Feedback:** No signal was detected at all, which is consistent with setup() never finishing: \`while (!Serial) { }\` on line 19 blocks forever when no USB serial terminal is connected, so the PWM configuration code after it (lines 21-33) never executes. Remove or bypass this blocking wait so the PWM setup runs unconditionally right after reset.
- **Where to look:** submission\_08.ino:19

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`duty_pct`)

- **Why:** nothing was measured for 'duty\_pct' (null, e.g. no signal or no response); expected ≈ 25% ± 1 pt
- **Feedback:** Duty cycle could not be measured because no edges were seen on D5, again pointing to setup() being stuck at \`while (!Serial) { }\` on line 19 before PWM0 is even enabled. Check whether the grading harness opens a serial connection; if not, this line prevents the PWM from ever starting, independent of whether COUNTERTOP/CMP values are correct.
- **Where to look:** submission\_08.ino:19

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`edge_count`)

- **Why:** measured 0, but expected ≥ 2
- **Feedback:** Zero edges were counted on D5, meaning the pin never toggled after reset. This matches the blocking \`while (!Serial) { }\` loop at line 19, which halts execution before PSEL.OUT, ENABLE, and TASKS\_SEQSTART are set in lines 21-33. Confirm by removing the Serial wait (or replacing it with a timeout) and re-testing without a terminal attached.
- **Where to look:** submission\_08.ino:19

## Not graded automatically

- **Must use a hardware timer/PWM peripheral (not analogWrite() or delay()-based bit-banging).**: Not electrically observable: a correctly timed 1 kHz/25% waveform can be produced by either a hardware timer or careful software timing; this can only be checked by TA code review.
- **Register values/constants are commented and their computation explained.**: Code documentation/comments cannot be verified electrically; requires manual review of the submitted source.

## Assumptions the grader made

- No tolerance was given for frequency, so a default of tol\_pct: 2 is used.
- No tolerance was given for duty cycle, so a default of tol\_abs: 1 percentage point is used.
- A 500 ms measurement window is used, giving ~500 periods of the 1 kHz signal for a stable frequency/duty measurement.
- Requirement 2 (signal starts on its own after reset) is verified implicitly by measuring the waveform right after the mandatory 1000 ms boot wait, with no stimulus step preceding it.
