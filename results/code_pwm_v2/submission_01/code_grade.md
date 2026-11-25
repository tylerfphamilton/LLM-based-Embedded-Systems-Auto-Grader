# Code-only grade: submission_01

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The signal on pin D5 must have a frequency of 1 kHz. | FAIL | PRESCALER\_DIV\_16 gives a 1 MHz PWM clock (1 tick = 1 us), and COUNTERTOP=1000 would give 1 kHz in Up mode, but MODE is set to PWM\_MODE\_UPDOWN\_UpAndDown. In up-and-down (center-aligned) mode the counter counts 0-\>COUNTERTOP-\>0, so the actual period is 2\*COUNTERTOP = 2000 ticks = 2 ms, i.e. 500 Hz, not 1 kHz. This is exactly the factor-of-two prescaler/countertop mistake the handout warns about. (submission\_01.ino:30) |
| The signal on pin D5 must have a duty cycle of 25%. | PASS | In up-and-down mode the output is high for CMP ticks on the way up and CMP ticks on the way down out of a total period of 2\*COUNTERTOP, preserving the ratio CMP/COUNTERTOP = 250/1000 = 25%. The polarity bit (0x8000) is set so the compare value represents HIGH time as the comment explains, so the duty ratio is correct even though the overall period is doubled. (submission\_01.ino:19) |
| The PWM signal on D5 must start automatically after reset without any serial input or button press. | PASS | All PWM configuration and NRF\_PWM0-\>TASKS\_SEQSTART\[0\] = 1 are executed unconditionally inside setup(), with no dependency on serial input or button presses, so the signal starts automatically after reset. (submission\_01.ino:42) |
| The PWM signal on D5 must be stable (correct frequency and duty cycle) within 50 ms after reset. | FAIL | Although the PWM hardware is started immediately in setup() with no delay (so timing-wise it would be stable quickly), the configured frequency is permanently wrong (500 Hz instead of 1 kHz) due to the UpAndDown mode doubling the period, so the signal never reaches the required correct frequency/duty combination, including within the first 50 ms. (submission\_01.ino:30) |
