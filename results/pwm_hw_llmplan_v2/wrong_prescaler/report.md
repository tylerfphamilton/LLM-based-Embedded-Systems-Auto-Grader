# Autograder report: pwm_1khz_llm_v2

**Submission:** `wrong_prescaler`  
**Result: 2 of 3 checks passed** · 1 failed · 0 borderline · 0 could not be measured

> Verify that the student's Nano 33 BLE Sense generates a free-running 1 kHz, 25% duty cycle square wave on D5 immediately after reset, without any stimulus.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. | `frequency_hz` | ≈ 1000 Hz ± 2% | 505.47 Hz | ❌ FAIL |
| The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. | `duty_pct` | ≈ 25% ± 1 pt | 25% | ✅ PASS |
| The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. | `edge_count` | ≥ 2 | 253 | ✅ PASS |

## What to fix

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`frequency_hz`)

- **Why:** measured 505.47 Hz, but expected ≈ 1000 Hz ± 2%
- **Feedback:** The computed period\_us on line 14 evaluates to 2000 µs (32 \* 1000 \* 1e6 / 16e6), which yields a 500 Hz signal instead of the intended 1000 Hz — matching the measured ~505 Hz. The PRESCALER (32) or COUNTER\_TOP (1000) constants are set to produce double the desired period; halving PRESCALER to 16 (or COUNTER\_TOP to 500) would give the correct 1000 µs period. Check the arithmetic on line 14 and verify period\_us before calling pwm.period\_us().
- **Where to look:** wrong\_prescaler.ino:14

## Not graded automatically

- **Must use a hardware timer/PWM peripheral (not analogWrite() or delay()-based bit-banging).**: Not electrically observable: a correctly timed 1 kHz/25% waveform can be produced by either a hardware timer or careful software timing; this can only be checked by TA code review.
- **Register values/constants are commented and their computation explained.**: Code documentation/comments cannot be verified electrically; requires manual review of the submitted source.

## Assumptions the grader made

- No tolerance was given for frequency, so a default of tol\_pct: 2 is used.
- No tolerance was given for duty cycle, so a default of tol\_abs: 1 percentage point is used.
- A 500 ms measurement window is used, giving ~500 periods of the 1 kHz signal for a stable frequency/duty measurement.
- Requirement 2 (signal starts on its own after reset) is verified implicitly by measuring the waveform right after the mandatory 1000 ms boot wait, with no stimulus step preceding it.
