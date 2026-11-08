# Autograder report: pwm_1khz

**Submission:** `borderline`  
**Result: 1 of 2 checks passed** · 1 failed · 0 borderline · 0 could not be measured

> Generate a 1 kHz PWM signal with 25% duty cycle on pin D5.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| D5 outputs a 1 kHz PWM signal with 25% duty cycle | `frequency_hz` | ≈ 1000 Hz ± 2% | 1029.9 Hz | ❌ FAIL |
| D5 outputs a 1 kHz PWM signal with 25% duty cycle | `duty_pct` | ≈ 25% ± 1 pt | 24.97% | ✅ PASS |

## What to fix

### ❌ D5 outputs a 1 kHz PWM signal with 25% duty cycle (`frequency_hz`)

- **Why:** measured 1029.9 Hz, but expected ≈ 1000 Hz ± 2%
- **Feedback:** The constant PERIOD\_US is set to 981 instead of 1000, so pwm.period\_us(PERIOD\_US) configures a period of 0.981 ms rather than 1 ms. That corresponds to a frequency of about 1019-1030 Hz depending on timer rounding, matching the measured 1029.9 Hz. Change PERIOD\_US to 1000 to hit the 1 kHz target.
- **Where to look:** borderline.ino:6

## Not graded automatically

- **Use a hardware timer (not analogWrite or a delay loop)**: Not observable electrically

## Assumptions the grader made

- Handout gives no tolerance; assumed ±2% frequency and ±1 percentage point duty cycle
- Signal is stable 500 ms after reset
