# Autograder report: pwm_1khz_llm_v2

**Submission:** `submission_05`  
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
- **Feedback:** No edges at all were seen on D5, so no PWM waveform is reaching the pin. The PWM peripheral's PSEL.OUT is configured in pwm\_driver\_start(), but the GPIO pin itself is never configured as an output (no pinMode()/PIN\_CNF.DIR write anywhere in submission\_05.ino or pwm\_driver.cpp). On the nRF52, assigning a peripheral via PSEL is not enough; the pin's direction register must also be set to output or it stays high-impedance/input and the peripheral signal never appears externally.
- **Where to look:** pwm\_driver.cpp:11

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`duty_pct`)

- **Why:** nothing was measured for 'duty\_pct' (null, e.g. no signal or no response); expected ≈ 25% ± 1 pt
- **Feedback:** Duty cycle can't be measured because zero edges were captured on D5 - same root cause as the missing frequency: the pin is never put into output mode, so the PWM channel's compare/COUNTERTOP values (which otherwise correctly compute to 1000 Hz/25%) never reach the physical pin. Check that pinMode(D5, OUTPUT) or an equivalent nrf\_gpio\_cfg\_output() call happens before or inside pwm\_driver\_start().
- **Where to look:** pwm\_driver.cpp:11

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`edge_count`)

- **Why:** measured 0, but expected ≥ 2
- **Feedback:** Zero edges were detected, meaning D5 never toggled at all. This matches the absence of any GPIO direction/output configuration for the pin in pwm\_driver\_start() or setup(); only PSEL.OUT is written, which tells the PWM peripheral which pin to drive but does not itself make that pin an output. Add the missing pin-direction setup and re-check the waveform.
- **Where to look:** submission\_05.ino:19

## Not graded automatically

- **Must use a hardware timer/PWM peripheral (not analogWrite() or delay()-based bit-banging).**: Not electrically observable: a correctly timed 1 kHz/25% waveform can be produced by either a hardware timer or careful software timing; this can only be checked by TA code review.
- **Register values/constants are commented and their computation explained.**: Code documentation/comments cannot be verified electrically; requires manual review of the submitted source.

## Assumptions the grader made

- No tolerance was given for frequency, so a default of tol\_pct: 2 is used.
- No tolerance was given for duty cycle, so a default of tol\_abs: 1 percentage point is used.
- A 500 ms measurement window is used, giving ~500 periods of the 1 kHz signal for a stable frequency/duty measurement.
- Requirement 2 (signal starts on its own after reset) is verified implicitly by measuring the waveform right after the mandatory 1000 ms boot wait, with no stimulus step preceding it.
