# Code-only grade: wrong_pin

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The signal on pin D5 must have a frequency of 1 kHz. | FAIL | The PWM object is attached to D6 (line 10: \`const int PWM\_PIN = D6;\`, line 12 uses digitalPinToPinName(PWM\_PIN)), not D5, so there is no 1 kHz signal present on pin D5 at all. (wrong\_pin.ino:10) |
| The signal on pin D5 must have a duty cycle of 25%. | FAIL | The 25% duty cycle set via pwm.write(DUTY) in setup() is applied to the PwmOut object bound to D6 (line 10/12), so pin D5 never receives this signal. (wrong\_pin.ino:10) |
| The PWM signal on D5 must start automatically after reset without any serial input or button press. | FAIL | While the PwmOut peripheral does start automatically in setup() without user input, it is configured on D6 instead of D5 (line 10), so no PWM signal auto-starts on the required pin D5. (wrong\_pin.ino:10) |
| The PWM signal on D5 must be stable (correct frequency and duty cycle) within 50 ms after reset. | FAIL | Even though the PWM hardware would stabilize quickly after setup() runs, the signal appears on D6 (line 10) rather than D5, so there is no stable PWM on D5 within 50 ms or at any time. (wrong\_pin.ino:10) |
