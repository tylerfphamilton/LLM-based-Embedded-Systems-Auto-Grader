# Code-only grade: correct_alt_style

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The signal on pin D5 must have a frequency of 1 kHz. | PASS | wave-\>period\_ms(1) sets the PWM period to 1 ms, i.e. 1 kHz, using mbed's PwmOut which drives the nRF52840 hardware PWM peripheral. (correct\_alt\_style.ino:14) |
| The signal on pin D5 must have a duty cycle of 25%. | PASS | wave-\>pulsewidth\_us(250) with a 1000 us period sets the high time to 250/1000 = 25% duty cycle. (correct\_alt\_style.ino:15) |
| The PWM signal on D5 must start automatically after reset without any serial input or button press. | PASS | startWave() is called directly from setup(), so the PWM begins automatically at boot with no serial or button input required; loop() only delays. (correct\_alt\_style.ino:18-19) |
| The PWM signal on D5 must be stable (correct frequency and duty cycle) within 50 ms after reset. | PASS | The PwmOut object is configured synchronously in setup() before loop() begins, so the hardware PWM peripheral starts outputting the correct waveform essentially immediately after reset, well within 50 ms. (correct\_alt\_style.ino:12-16) |
