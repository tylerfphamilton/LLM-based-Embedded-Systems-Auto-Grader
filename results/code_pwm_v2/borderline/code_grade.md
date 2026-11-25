# Code-only grade: borderline

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The signal on pin D5 must have a frequency of 1 kHz. | FAIL | PERIOD\_US is set to 981 instead of 1000, giving a period of 981 µs and a frequency of 1/981e-6 ≈ 1019.4 Hz, not the required 1 kHz. This is a deterministic miscalculation of the period constant, not timing jitter. (borderline.ino:6) |
| The signal on pin D5 must have a duty cycle of 25%. | PASS | pwm.write(DUTY) is called with DUTY = 0.25f, which sets the PwmOut duty cycle to exactly 25% regardless of the period value. (borderline.ino:13) |
| The PWM signal on D5 must start automatically after reset without any serial input or button press. | PASS | setup() configures and starts the PwmOut peripheral unconditionally with no wait for Serial input or button press, so the PWM begins automatically on reset. (borderline.ino:11) |
| The PWM signal on D5 must be stable (correct frequency and duty cycle) within 50 ms after reset. | FAIL | Although the PWM is configured immediately in setup() and is stable within milliseconds of boot, the configured frequency (~1019 Hz from PERIOD\_US=981) is incorrect, so the signal that stabilizes quickly is not the correct 1 kHz/25% waveform. (borderline.ino:6) |
