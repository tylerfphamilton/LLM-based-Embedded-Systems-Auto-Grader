# Autograder report: pwm_1khz_llm_v2

**Submission:** `wrong_pin`  
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
- **Feedback:** No signal was detected on D5 because the student configured the PWM output on the wrong pin: \`PWM\_PIN\` is set to \`D6\` instead of \`D5\` (wrong\_pin.ino:10). Since \`mbed::PwmOut pwm(...)\` is instantiated with this pin, all PWM activity happens on D6, leaving D5 silent. Check the \`PWM\_PIN\` constant and change it to \`D5\`.
- **Where to look:** wrong\_pin.ino:10

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`duty_pct`)

- **Why:** nothing was measured for 'duty\_pct' (null, e.g. no signal or no response); expected ≈ 25% ± 1 pt
- **Feedback:** Duty cycle could not be measured because the PWM signal is being driven on D6, not D5, due to \`const int PWM\_PIN = D6;\` at wrong\_pin.ino:10. Fixing the pin assignment so \`pwm\` is constructed with \`D5\` should let the duty cycle be measured on the correct pin.
- **Where to look:** wrong\_pin.ino:10

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`edge_count`)

- **Why:** measured 0, but expected ≥ 2
- **Feedback:** Zero edges were detected on D5 because the PWM peripheral is actually toggling D6, as set by \`const int PWM\_PIN = D6;\` (wrong\_pin.ino:10) and used in \`mbed::PwmOut pwm(digitalPinToPinName(PWM\_PIN));\` (wrong\_pin.ino:12). Correct the pin constant to D5 to route the hardware PWM to the expected test point.
- **Where to look:** wrong\_pin.ino:10

## Not graded automatically

- **Must use a hardware timer/PWM peripheral (not analogWrite() or delay()-based bit-banging).**: Not electrically observable: a correctly timed 1 kHz/25% waveform can be produced by either a hardware timer or careful software timing; this can only be checked by TA code review.
- **Register values/constants are commented and their computation explained.**: Code documentation/comments cannot be verified electrically; requires manual review of the submitted source.

## Assumptions the grader made

- No tolerance was given for frequency, so a default of tol\_pct: 2 is used.
- No tolerance was given for duty cycle, so a default of tol\_abs: 1 percentage point is used.
- A 500 ms measurement window is used, giving ~500 periods of the 1 kHz signal for a stable frequency/duty measurement.
- Requirement 2 (signal starts on its own after reset) is verified implicitly by measuring the waveform right after the mandatory 1000 ms boot wait, with no stimulus step preceding it.
