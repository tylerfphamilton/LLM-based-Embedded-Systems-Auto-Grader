# Autograder report: pwm_1khz_llm_v2

**Submission:** `submission_09`  
**Result: 1 of 3 checks passed** · 2 failed · 0 borderline · 0 could not be measured

> Verify that the student's Nano 33 BLE Sense generates a free-running 1 kHz, 25% duty cycle square wave on D5 immediately after reset, without any stimulus.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. | `frequency_hz` | ≈ 1000 Hz ± 2% | 15.426 Hz | ❌ FAIL |
| The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. | `duty_pct` | ≈ 25% ± 1 pt | 98.86% | ❌ FAIL |
| The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. | `edge_count` | ≥ 2 | 8 | ✅ PASS |

## What to fix

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`frequency_hz`)

- **Why:** measured 15.426 Hz, but expected ≈ 1000 Hz ± 2%
- **Feedback:** TIMER2 is never cleared when it reaches CC\[1\] (1000us) — there's no SHORTS\_COMPARE1\_CLEAR set, so the 16-bit timer keeps counting past 1000 all the way to 65535 ticks (~65.5 ms) before wrapping to 0, where it then re-triggers the two PPI/GPIOTE toggles. That gives a real period of ~65.5 ms (~15.3 Hz), matching the measured 15.426 Hz. Add 'NRF\_TIMER2-\>SHORTS = TIMER\_SHORTS\_COMPARE1\_CLEAR\_Msk;' after setting CC\[1\] (around line 43) so the timer resets to 0 at the end of each 1000us period.
- **Where to look:** submission\_09.ino:43

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`duty_pct`)

- **Why:** measured 98.86%, but expected ≈ 25% ± 1 pt
- **Feedback:** Because the timer is never cleared at CC\[1\] (missing TIMER\_SHORTS\_COMPARE1\_CLEAR), the pin toggles low at 250us and back high at 1000us as intended, but then stays high for the remaining ~64536us until the 16-bit timer wraps around and finally reaches CC\[0\]/CC\[1\] again. That makes the pin high for the vast majority of the (much longer) actual period, producing the measured ~98.86% duty cycle instead of 25%. Adding the missing SHORTS to clear TIMER2 on COMPARE\[1\] (near line 43, after CC\[0\]/CC\[1\] setup) will restore the correct 250us-high/750us-low pattern.
- **Where to look:** submission\_09.ino:43

## Not graded automatically

- **Must use a hardware timer/PWM peripheral (not analogWrite() or delay()-based bit-banging).**: Not electrically observable: a correctly timed 1 kHz/25% waveform can be produced by either a hardware timer or careful software timing; this can only be checked by TA code review.
- **Register values/constants are commented and their computation explained.**: Code documentation/comments cannot be verified electrically; requires manual review of the submitted source.

## Assumptions the grader made

- No tolerance was given for frequency, so a default of tol\_pct: 2 is used.
- No tolerance was given for duty cycle, so a default of tol\_abs: 1 percentage point is used.
- A 500 ms measurement window is used, giving ~500 periods of the 1 kHz signal for a stable frequency/duty measurement.
- Requirement 2 (signal starts on its own after reset) is verified implicitly by measuring the waveform right after the mandatory 1000 ms boot wait, with no stimulus step preceding it.
