# Autograder report: pwm_1khz_llm_v2

**Submission:** `submission_03`  
**Result: 2 of 3 checks passed** · 1 failed · 0 borderline · 0 could not be measured

> Verify that the student's Nano 33 BLE Sense generates a free-running 1 kHz, 25% duty cycle square wave on D5 immediately after reset, without any stimulus.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. | `frequency_hz` | ≈ 1000 Hz ± 2% | 252.75 Hz | ❌ FAIL |
| The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. | `duty_pct` | ≈ 25% ± 1 pt | 25% | ✅ PASS |
| The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. | `edge_count` | ≥ 2 | 126 | ✅ PASS |

## What to fix

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`frequency_hz`)

- **Why:** measured 252.75 Hz, but expected ≈ 1000 Hz ± 2%
- **Feedback:** Measured frequency is about 1/4 of the target (252.75 Hz vs 1000 Hz), and 1000/252.749 ≈ 3.96 ≈ 4, so COUNTERTOP is effectively 4x too large. This points to the CORE\_CLK\_HZ constant on line 15: the nRF52840's PWM peripheral is clocked from the 16 MHz HFCLK, not the 64 MHz CPU clock, so PWM\_TOP\_VAL (line 19) comes out 4x too big (4000 instead of 1000) for PRESCALER DIV\_16. Check the actual PWM clock source in the datasheet and recompute PWM\_TOP\_VAL using 16 MHz as the base clock.
- **Where to look:** submission\_03.ino:15

## Not graded automatically

- **Must use a hardware timer/PWM peripheral (not analogWrite() or delay()-based bit-banging).**: Not electrically observable: a correctly timed 1 kHz/25% waveform can be produced by either a hardware timer or careful software timing; this can only be checked by TA code review.
- **Register values/constants are commented and their computation explained.**: Code documentation/comments cannot be verified electrically; requires manual review of the submitted source.

## Assumptions the grader made

- No tolerance was given for frequency, so a default of tol\_pct: 2 is used.
- No tolerance was given for duty cycle, so a default of tol\_abs: 1 percentage point is used.
- A 500 ms measurement window is used, giving ~500 periods of the 1 kHz signal for a stable frequency/duty measurement.
- Requirement 2 (signal starts on its own after reset) is verified implicitly by measuring the waveform right after the mandatory 1000 ms boot wait, with no stimulus step preceding it.
