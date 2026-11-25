# Code-only grade: wrong_prescaler

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The signal on pin D5 must have a frequency of 1 kHz. | FAIL | period\_us = PRESCALER\*COUNTER\_TOP\*1e6/BASE\_CLOCK\_HZ = 32\*1000\*1e6/16e6 = 2000 microseconds, giving a period of 2 ms and frequency of 500 Hz, not the required 1 kHz (the comments even confirm a 500 kHz tick with 1000 ticks/period = 2 ms period). (wrong\_prescaler.ino:14) |
| The signal on pin D5 must have a duty cycle of 25%. | PASS | pwm.write(DUTY) with DUTY = 0.25f sets the PWM duty cycle to 25% of whatever period is configured, independent of the period miscalculation, so the duty cycle itself is correct. (wrong\_prescaler.ino:16) |
| The PWM signal on D5 must start automatically after reset without any serial input or button press. | PASS | setup() configures and starts the mbed::PwmOut immediately on boot with no dependency on Serial input or button presses, so the signal (albeit at the wrong frequency) starts automatically after reset. (wrong\_prescaler.ino:13) |
| The PWM signal on D5 must be stable (correct frequency and duty cycle) within 50 ms after reset. | FAIL | Although PwmOut begins outputting quickly after setup(), the frequency it produces is 500 Hz (due to the period\_us miscalculation) rather than the required 1 kHz, so the signal never settles to the correct frequency/duty combination, regardless of timing after reset. (wrong\_prescaler.ino:14) |
