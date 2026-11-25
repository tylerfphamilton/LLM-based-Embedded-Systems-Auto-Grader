# Code-only grade: wrong_duty

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The signal on pin D5 must have a frequency of 1 kHz. | PASS | period\_us is computed as PRESCALER\*COUNTER\_TOP\*1e6/BASE\_CLOCK\_HZ = 16\*1000\*1e6/16e6 = 1000 us, giving a 1 ms period i.e. 1 kHz, and pwm.period\_us() sets this correctly in setup(). (wrong\_duty.ino:14-15) |
| The signal on pin D5 must have a duty cycle of 25%. | FAIL | COMPARE is set to COUNTER\_TOP/2 (line 9), so pwm.write(COMPARE/COUNTER\_TOP) sets a 50% duty cycle instead of the required 25%. (wrong\_duty.ino:9) |
| The PWM signal on D5 must start automatically after reset without any serial input or button press. | PASS | The PWM is configured and started inside setup(), which runs automatically after reset with no serial input or button press required; loop() does nothing further. (wrong\_duty.ino:13-17) |
| The PWM signal on D5 must be stable (correct frequency and duty cycle) within 50 ms after reset. | PASS | The hardware PWM peripheral (mbed::PwmOut) is configured once in setup() and runs autonomously in hardware from that point, so the (wrong-duty but otherwise fixed-frequency) waveform becomes stable essentially immediately after reset, well within 50 ms. (wrong\_duty.ino:11-17) |
