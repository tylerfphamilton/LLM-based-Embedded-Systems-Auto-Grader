# Code-only grade: too_slow

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | In setup(), digitalWrite(LED\_BUILTIN, LOW) is called right after pinMode(LED\_BUILTIN, OUTPUT), so the LED starts off after reset. (too\_slow.ino:8) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | Each detected press flips ledOn and writes it to LED\_BUILTIN (line 16-17), and the while-loop waiting for release (line 19-21) ensures one toggle is registered per press/release cycle, alternating ON/OFF correctly. (too\_slow.ino:16) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | FAIL | The LED is only toggled after a blocking delay(35) (line 14), so the visible reaction to a press is delayed by 35 ms, exceeding the 20 ms 'no noticeable delay' requirement. (too\_slow.ino:14) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | The code re-checks the pin after a 35 ms delay (lines 13-15) and only toggles if still LOW, then blocks until release (line 19-21), which prevents bounce from causing multiple toggles for a single press. (too\_slow.ino:13) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | PASS | On every confirmed toggle, Serial1.println(ledOn ? "ON" : "OFF") prints the new state on its own line. (too\_slow.ino:18) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | Serial1.begin(9600) is used in setup and Serial1.println is used for output; the USB Serial object is never referenced. (too\_slow.ino:9) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | pinMode(2, INPUT\_PULLUP) configures D2 with the internal pull-up as required. (too\_slow.ino:6) |
