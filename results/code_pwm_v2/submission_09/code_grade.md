# Code-only grade: submission_09

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The signal on pin D5 must have a frequency of 1 kHz. | FAIL | TIMER2 is configured as a free-running 16-bit timer (BITMODE\_16Bit) with CC\[0\]=250 and CC\[1\]=1000, but the code never sets NRF\_TIMER2-\>SHORTS to clear the counter on COMPARE\[1\] match. Without that shortcut the counter does not reset at 1000us; it keeps counting up to the 16-bit wrap at 65536us before the 250/1000 compare events fire again, so the actual toggle period is ~65.536 ms (≈15.26 Hz), not 1 kHz. (submission\_09.ino:41-43) |
| The signal on pin D5 must have a duty cycle of 25%. | FAIL | Because the timer free-runs to 65535 before wrapping (no SHORTS\_COMPARE1\_CLEAR), the pin is only low from the 250us toggle until the 1000us toggle each 65536us cycle, then stays high for the remaining ~64786us before the next 250us mark. This yields a duty cycle near 98.9% high, not the intended 25%. (submission\_09.ino:36-53) |
| The PWM signal on D5 must start automatically after reset without any serial input or button press. | PASS | All GPIOTE/TIMER/PPI configuration and NRF\_TIMER2-\>TASKS\_START=1 happen inside setup(), which runs automatically after reset with no serial or button input required. (submission\_09.ino:28-53) |
| The PWM signal on D5 must be stable (correct frequency and duty cycle) within 50 ms after reset. | FAIL | Since the missing SHORTS\_COMPARE1\_CLEAR causes the timer to run with a ~65.5ms period instead of 1ms, the output never settles into the correct 1kHz/25% waveform at all, let alone within 50ms of reset; the first full observed cycle already shows the wrong timing. (submission\_09.ino:41-43) |
