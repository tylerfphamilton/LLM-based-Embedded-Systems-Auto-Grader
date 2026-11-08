# Autograder report: pwm_1khz

**Submission:** `broken`  
**Result: 0 of 2 checks passed** · 2 failed · 0 borderline · 0 could not be measured

> Generate a 1 kHz PWM signal with 25% duty cycle on pin D5.

**Your sketch did not compile, so no checks were run.**

```

[92mUsed platform[0m     [92mVersion[0m [90mPath[0m
[93marduino:mbed_nano[0m 4.6.0   [90mC:\Users\seanh\AppData\Local\Arduino15\packages\arduino\hardware\mbed_nano\4.6.0[0m
C:\Users\seanh\embedded_autograder\LLM-based-Embedded-Systems-Auto-Grader\benchmark\pwm_1khz\broken\broken.ino:13:1: error: expected ',' or ';' before 'void'
 void setup() {
 ^~~~
Error during build: exit status 1

```

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| D5 outputs a 1 kHz PWM signal with 25% duty cycle | `frequency_hz` | ≈ 1000 Hz ± 2% | no value (null) | ❌ FAIL |
| D5 outputs a 1 kHz PWM signal with 25% duty cycle | `duty_pct` | ≈ 25% ± 1 pt | no value (null) | ❌ FAIL |

## What to fix

### ❌ D5 outputs a 1 kHz PWM signal with 25% duty cycle (`frequency_hz`)

- **Why:** the sketch did not compile
- **Feedback:** The sketch fails to compile because the declaration of \`pwm\` on line 11 is missing a terminating semicolon, which causes a syntax error. Since compilation fails, no PWM output can be measured. Add a \`;\` at the end of line 11.
- **Where to look:** broken.ino:11

### ❌ D5 outputs a 1 kHz PWM signal with 25% duty cycle (`duty_pct`)

- **Why:** the sketch did not compile
- **Feedback:** Same root cause as the frequency check: the missing semicolon after \`mbed::PwmOut pwm(digitalPinToPinName(D5))\` on line 11 prevents the sketch from compiling, so the duty cycle could not be measured. Fix the syntax error and re-flash to get a measurable signal.
- **Where to look:** broken.ino:11

## Not graded automatically

- **Use a hardware timer (not analogWrite or a delay loop)**: Not observable electrically

## Assumptions the grader made

- Handout gives no tolerance; assumed ±2% frequency and ±1 percentage point duty cycle
- Signal is stable 500 ms after reset
