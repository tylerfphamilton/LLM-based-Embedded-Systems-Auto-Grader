# Autograder report: pwm_1khz_llm_v2

**Submission:** `broken`  
**Result: 0 of 3 checks passed** · 3 failed · 0 borderline · 0 could not be measured

> Verify that the student's Nano 33 BLE Sense generates a free-running 1 kHz, 25% duty cycle square wave on D5 immediately after reset, without any stimulus.

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
| The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. | `frequency_hz` | ≈ 1000 Hz ± 2% | no value (null) | ❌ FAIL |
| The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. | `duty_pct` | ≈ 25% ± 1 pt | no value (null) | ❌ FAIL |
| The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. | `edge_count` | ≥ 2 | no value (null) | ❌ FAIL |

## What to fix

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`frequency_hz`)

- **Why:** the sketch did not compile
- **Feedback:** The sketch fails to compile because line 11 is missing a terminating semicolon after the PwmOut object declaration: \`mbed::PwmOut pwm(digitalPinToPinName(D5))\`. This causes a syntax error that prevents the rest of the file from compiling, so no frequency could be measured. Add a \`;\` at the end of line 11.
- **Where to look:** broken.ino:11

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`duty_pct`)

- **Why:** the sketch did not compile
- **Feedback:** Same root cause as the frequency check: the missing semicolon on line 11 after \`mbed::PwmOut pwm(digitalPinToPinName(D5))\` breaks compilation, so no duty cycle could be measured. Fix the declaration by terminating it with a semicolon.
- **Where to look:** broken.ino:11

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`edge_count`)

- **Why:** the sketch did not compile
- **Feedback:** No edges were detected because the sketch never ran on the board; it did not compile due to the missing semicolon at the end of line 11 (\`mbed::PwmOut pwm(digitalPinToPinName(D5))\`). Correct this syntax error and the signal edges should become measurable.
- **Where to look:** broken.ino:11

## Not graded automatically

- **Must use a hardware timer/PWM peripheral (not analogWrite() or delay()-based bit-banging).**: Not electrically observable: a correctly timed 1 kHz/25% waveform can be produced by either a hardware timer or careful software timing; this can only be checked by TA code review.
- **Register values/constants are commented and their computation explained.**: Code documentation/comments cannot be verified electrically; requires manual review of the submitted source.

## Assumptions the grader made

- No tolerance was given for frequency, so a default of tol\_pct: 2 is used.
- No tolerance was given for duty cycle, so a default of tol\_abs: 1 percentage point is used.
- A 500 ms measurement window is used, giving ~500 periods of the 1 kHz signal for a stable frequency/duty measurement.
- Requirement 2 (signal starts on its own after reset) is verified implicitly by measuring the waveform right after the mandatory 1000 ms boot wait, with no stimulus step preceding it.
