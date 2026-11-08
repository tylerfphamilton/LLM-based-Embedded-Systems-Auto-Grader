# Autograder report: pwm_1khz

**Submission:** `wrong_duty`  
**Result: 1 of 2 checks passed** · 1 failed · 0 borderline · 0 could not be measured

> Generate a 1 kHz PWM signal with 25% duty cycle on pin D5.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| D5 outputs a 1 kHz PWM signal with 25% duty cycle | `frequency_hz` | ≈ 1000 Hz ± 2% | 1009.5 Hz | ✅ PASS |
| D5 outputs a 1 kHz PWM signal with 25% duty cycle | `duty_pct` | ≈ 25% ± 1 pt | 50% | ❌ FAIL |

## What to fix

### ❌ D5 outputs a 1 kHz PWM signal with 25% duty cycle (`duty_pct`)

- **Why:** measured 50%, but expected ≈ 25% ± 1 pt
- **Feedback:** The constant COMPARE on line 9 is set to COUNTER\_TOP / 2, which produces a 50% duty cycle instead of the required 25%. Since pwm.write() on line 16 uses COMPARE/COUNTER\_TOP as the duty fraction, this directly causes the measured 50% output. Change COMPARE to COUNTER\_TOP / 4 (or compute the fraction as 0.25 directly) to get the correct 25% duty cycle.
- **Where to look:** wrong\_duty.ino:9

## Not graded automatically

- **Use a hardware timer (not analogWrite or a delay loop)**: Not observable electrically

## Assumptions the grader made

- Handout gives no tolerance; assumed ±2% frequency and ±1 percentage point duty cycle
- Signal is stable 500 ms after reset
