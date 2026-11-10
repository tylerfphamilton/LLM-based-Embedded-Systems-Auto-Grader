# Autograder report: pwm_1khz_llm_v2

**Submission:** `submission_07`  
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
- **Feedback:** No signal is seen because the PWM sequence that was actually configured (SEQ\[0\]) is never started. In pwm\_start() the code calls NRF\_PWM0-\>TASKS\_SEQSTART\[1\] = 1, which starts sequence 1, but only SEQ\[0\] was set up with PTR/CNT/etc. Since SEQ\[1\] registers are left at their reset (zero) values, the peripheral has no valid duty data to play and produces no toggling output on D5.
- **Where to look:** submission\_07.ino:31

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`duty_pct`)

- **Why:** nothing was measured for 'duty\_pct' (null, e.g. no signal or no response); expected ≈ 25% ± 1 pt
- **Feedback:** Duty cycle can't be measured because, as with the frequency check, the wrong sequence index is triggered in pwm\_start(): TASKS\_SEQSTART\[1\] instead of TASKS\_SEQSTART\[0\]. The configured duty\_seq array (250 \| 0x8000) is referenced by SEQ\[0\], but that sequence is never started, so no PWM waveform with any duty cycle is ever produced on D5.
- **Where to look:** submission\_07.ino:31

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`edge_count`)

- **Why:** measured 0, but expected ≥ 2
- **Feedback:** Zero edges were measured, consistent with the PWM never actually starting. The fix should start in the same place: NRF\_PWM0-\>TASKS\_SEQSTART\[1\] in pwm\_start() starts the unconfigured sequence 1 rather than the configured sequence 0 (SEQ\[0\]). Check that this is changed to TASKS\_SEQSTART\[0\] so the configured duty\_seq data is actually played out on D5.
- **Where to look:** submission\_07.ino:31

## Not graded automatically

- **Must use a hardware timer/PWM peripheral (not analogWrite() or delay()-based bit-banging).**: Not electrically observable: a correctly timed 1 kHz/25% waveform can be produced by either a hardware timer or careful software timing; this can only be checked by TA code review.
- **Register values/constants are commented and their computation explained.**: Code documentation/comments cannot be verified electrically; requires manual review of the submitted source.

## Assumptions the grader made

- No tolerance was given for frequency, so a default of tol\_pct: 2 is used.
- No tolerance was given for duty cycle, so a default of tol\_abs: 1 percentage point is used.
- A 500 ms measurement window is used, giving ~500 periods of the 1 kHz signal for a stable frequency/duty measurement.
- Requirement 2 (signal starts on its own after reset) is verified implicitly by measuring the waveform right after the mandatory 1000 ms boot wait, with no stimulus step preceding it.
