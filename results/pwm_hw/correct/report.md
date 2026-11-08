# Autograder report: pwm_1khz

**Submission:** `correct`  
**Result: 2 of 2 checks passed** · 0 failed · 0 borderline · 0 could not be measured

> Generate a 1 kHz PWM signal with 25% duty cycle on pin D5.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| D5 outputs a 1 kHz PWM signal with 25% duty cycle | `frequency_hz` | ≈ 1000 Hz ± 2% | 1010.1 Hz | ✅ PASS |
| D5 outputs a 1 kHz PWM signal with 25% duty cycle | `duty_pct` | ≈ 25% ± 1 pt | 25% | ✅ PASS |

## Not graded automatically

- **Use a hardware timer (not analogWrite or a delay loop)**: Not observable electrically

## Assumptions the grader made

- Handout gives no tolerance; assumed ±2% frequency and ±1 percentage point duty cycle
- Signal is stable 500 ms after reset
