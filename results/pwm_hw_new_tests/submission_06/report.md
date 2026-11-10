# Autograder report: pwm_1khz_llm_v2

**Submission:** `submission_06`  
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
- **Feedback:** No signal was detected at all on D5, so frequency could not be measured. This matches NRF\_PWM3-\>LOOP being set to 0 (sketch.ino:26), which tells the PWM peripheral to play the sequence exactly once and then halt instead of looping forever; after the single 1 ms pulse the pin stops toggling. Check the LOOP register value needed for continuous operation (it is not simply 0 for infinite repeats).
- **Where to look:** submission\_06.ino:26

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`duty_pct`)

- **Why:** nothing was measured for 'duty\_pct' (null, e.g. no signal or no response); expected ≈ 25% ± 1 pt
- **Feedback:** Duty cycle could not be measured because the waveform stops after one cycle, so the scope/analyzer never captures a steady repeating high/low period to compute duty from. This is again due to NRF\_PWM3-\>LOOP = 0 in setup(), which disables the automatic re-triggering of SEQ\[0\] needed for a free-running signal. Verify what LOOP value corresponds to infinite looping for this peripheral.
- **Where to look:** submission\_06.ino:26

### ❌ The signal on D5 has a frequency of 1 kHz and a duty cycle of 25%, starting on its own right after reset. (`edge_count`)

- **Why:** measured 0, but expected ≥ 2
- **Feedback:** Only 0 edges were counted on D5 versus the expected ≥2, meaning the pin essentially never toggled during the measurement window. This is consistent with the sequence being started once via TASKS\_SEQSTART\[0\] (sketch.ino:35) but never restarted, because LOOP is set to 0 (sketch.ino:26) and REFRESH is 0 (sketch.ino:32), so the single sample plays once and the PWM task completes without looping. Check the required LOOP/REFRESH configuration for continuous (free-running) output.
- **Where to look:** submission\_06.ino:26

## Not graded automatically

- **Must use a hardware timer/PWM peripheral (not analogWrite() or delay()-based bit-banging).**: Not electrically observable: a correctly timed 1 kHz/25% waveform can be produced by either a hardware timer or careful software timing; this can only be checked by TA code review.
- **Register values/constants are commented and their computation explained.**: Code documentation/comments cannot be verified electrically; requires manual review of the submitted source.

## Assumptions the grader made

- No tolerance was given for frequency, so a default of tol\_pct: 2 is used.
- No tolerance was given for duty cycle, so a default of tol\_abs: 1 percentage point is used.
- A 500 ms measurement window is used, giving ~500 periods of the 1 kHz signal for a stable frequency/duty measurement.
- Requirement 2 (signal starts on its own after reset) is verified implicitly by measuring the waveform right after the mandatory 1000 ms boot wait, with no stimulus step preceding it.
