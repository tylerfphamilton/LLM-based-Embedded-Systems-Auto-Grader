# Autograder report: pwm_1khz_llm_v2

**Submission:** `submission_04`  
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
- **Feedback:** No frequency could be measured because no edges were detected on D5 at all, consistent with the PWM peripheral being disconnected from the pin due to the inverted CONNECT bit logic at line 28 (\`(1u \<\< PWM\_PSEL\_OUT\_CONNECT\_Pos)\`). Once the pin is actually connected (CONNECT = 0, not 1), the frequency measurement should become possible again.
- **Where to look:** submission\_04.ino:28

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`duty_pct`)

- **Why:** nothing was measured for 'duty\_pct' (null, e.g. no signal or no response); expected ≈ 25% ± 1 pt
- **Feedback:** Duty cycle could not be measured for the same reason the frequency could not: there is no signal on D5, likely because the PSEL.OUT CONNECT bit is set to 1 at line 28, which disconnects (rather than connects) the PWM peripheral from the GPIO pin on nRF52 hardware. Fix the CONNECT bit polarity and re-check the compare value (CMP=250 against TOP=1000) for duty cycle correctness afterward.
- **Where to look:** submission\_04.ino:28

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`edge_count`)

- **Why:** measured 0, but expected ≥ 2
- **Feedback:** No toggling is seen on D5 at all, which points to the PWM output never actually being connected to the pin. In nRF52's PSEL.OUT register the CONNECT field is active-low (0 = connected, 1 = disconnected), but the code writes \`(1u \<\< PWM\_PSEL\_OUT\_CONNECT\_Pos)\` at line 28, which actually disconnects the peripheral from the pin instead of connecting it. Check the PWM\_PSEL\_OUT\_CONNECT\_Pos usage against the nRF52 reference manual and use the Connected enum value (0) instead of 1.
- **Where to look:** submission\_04.ino:28

## Not graded automatically

- **Must use a hardware timer/PWM peripheral (not analogWrite() or delay()-based bit-banging).**: Not electrically observable: a correctly timed 1 kHz/25% waveform can be produced by either a hardware timer or careful software timing; this can only be checked by TA code review.
- **Register values/constants are commented and their computation explained.**: Code documentation/comments cannot be verified electrically; requires manual review of the submitted source.

## Assumptions the grader made

- No tolerance was given for frequency, so a default of tol\_pct: 2 is used.
- No tolerance was given for duty cycle, so a default of tol\_abs: 1 percentage point is used.
- A 500 ms measurement window is used, giving ~500 periods of the 1 kHz signal for a stable frequency/duty measurement.
- Requirement 2 (signal starts on its own after reset) is verified implicitly by measuring the waveform right after the mandatory 1000 ms boot wait, with no stimulus step preceding it.
