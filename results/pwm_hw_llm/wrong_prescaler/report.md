# Autograder report: pwm_1khz

**Submission:** `wrong_prescaler`  
**Result: 1 of 2 checks passed** · 1 failed · 0 borderline · 0 could not be measured

> Generate a 1 kHz PWM signal with 25% duty cycle on pin D5.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| D5 outputs a 1 kHz PWM signal with 25% duty cycle | `frequency_hz` | ≈ 1000 Hz ± 2% | 504.96 Hz | ❌ FAIL |
| D5 outputs a 1 kHz PWM signal with 25% duty cycle | `duty_pct` | ≈ 25% ± 1 pt | 25% | ✅ PASS |

## What to fix

### ❌ D5 outputs a 1 kHz PWM signal with 25% duty cycle (`frequency_hz`)

- **Why:** measured 504.96 Hz, but expected ≈ 1000 Hz ± 2%
- **Feedback:** The period calculation on line 14 (\`period\_us = PRESCALER \* COUNTER\_TOP \* 1e6 / BASE\_CLOCK\_HZ\`) evaluates to 2000 µs, i.e. 500 Hz, not the intended 1000 Hz. With PRESCALER=32 and COUNTER\_TOP=1000, the effective tick rate is 500 kHz, so 1000 ticks take 2 ms instead of 1 ms. Try halving COUNTER\_TOP to 500 (or halving PRESCALER to 16) so the computed period\_us equals 1000.
- **Where to look:** wrong\_prescaler.ino:14

## Not graded automatically

- **Use a hardware timer (not analogWrite or a delay loop)**: Not observable electrically

## Assumptions the grader made

- Handout gives no tolerance; assumed ±2% frequency and ±1 percentage point duty cycle
- Signal is stable 500 ms after reset
