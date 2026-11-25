# Code-only grade: submission_08

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The signal on pin D5 must have a frequency of 1 kHz. | PASS | PRESCALER is set to DIV\_16 (16 MHz / 16 = 1 MHz PWM clock) and COUNTERTOP is 1000, giving a period of 1000 ticks at 1 MHz = 1 ms, i.e. 1 kHz. MODE is UPDOWN\_Up (simple up-counting), so the period/frequency math is correct regardless of the compare value or polarity bit. (submission\_08.ino:24) |
| The signal on pin D5 must have a duty cycle of 25%. | FAIL | seq0\[0\] is set to PWM\_CMP \| 0x8000 (line 15), which sets the nRF52 PWM polarity bit (bit 15) to 1, i.e. inverted polarity. With inverted polarity the output is LOW for the first COMPARE (250) ticks and HIGH for the remaining TOP-COMPARE (750) ticks, producing a 75% high duty cycle instead of the intended 25%. Normal polarity (bit 15 = 0) would have given the intended 25% high time for COMPARE=250/TOP=1000. (submission\_08.ino:15) |
| The PWM signal on D5 must start automatically after reset without any serial input or button press. | FAIL | setup() contains \`while (!Serial) { }\` (line 19), which on the Nano 33 BLE's native USB CDC serial blocks execution until a host opens the serial port/monitor. All PWM initialization occurs after this line, so the PWM will not start automatically after reset unless a host connects to the serial port, violating the no-interaction requirement. (submission\_08.ino:19) |
| The PWM signal on D5 must be stable (correct frequency and duty cycle) within 50 ms after reset. | FAIL | Because PWM setup is gated behind \`while (!Serial) { }\` (line 19), the PWM registers are not configured until a serial host connection is established, which will not happen within 50 ms of reset in the grader's automated measurement (and may never happen without manual action), so the signal is not guaranteed stable within 50 ms. (submission\_08.ino:19) |
