# Autograder report: pwm_1khz

**Submission:** `wrong_pin`  
**Result: 0 of 2 checks passed** · 2 failed · 0 borderline · 0 could not be measured

> Generate a 1 kHz PWM signal with 25% duty cycle on pin D5.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| D5 outputs a 1 kHz PWM signal with 25% duty cycle | `frequency_hz` | ≈ 1000 Hz ± 2% | no value (null) | ❌ FAIL |
| D5 outputs a 1 kHz PWM signal with 25% duty cycle | `duty_pct` | ≈ 25% ± 1 pt | no value (null) | ❌ FAIL |

## What to fix

### ❌ D5 outputs a 1 kHz PWM signal with 25% duty cycle (`frequency_hz`)

- **Why:** nothing was measured for 'frequency\_hz' (null, e.g. no signal or no response); expected ≈ 1000 Hz ± 2%
- **Feedback:** No signal was detected on D5 because the code actually configures PWM on D6 (see PWM\_PIN = D6 on line 10, used to construct the PwmOut object on line 12). Change PWM\_PIN to D5 so the PwmOut instance drives the correct pin.
- **Where to look:** wrong\_pin.ino:10

### ❌ D5 outputs a 1 kHz PWM signal with 25% duty cycle (`duty_pct`)

- **Why:** nothing was measured for 'duty\_pct' (null, e.g. no signal or no response); expected ≈ 25% ± 1 pt
- **Feedback:** Since the PWM output is actually being generated on D6 instead of D5 (PWM\_PIN = D6 on line 10), the measurement probe on D5 sees no signal at all, so duty cycle cannot be measured. Fixing the pin assignment to D5 should resolve this as well.
- **Where to look:** wrong\_pin.ino:10

## Not graded automatically

- **Use a hardware timer (not analogWrite or a delay loop)**: Not observable electrically

## Assumptions the grader made

- Handout gives no tolerance; assumed ±2% frequency and ±1 percentage point duty cycle
- Signal is stable 500 ms after reset
