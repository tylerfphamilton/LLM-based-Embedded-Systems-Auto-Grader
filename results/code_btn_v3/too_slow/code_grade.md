# Code-only grade: too_slow

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | setup() explicitly calls digitalWrite(LED\_BUILTIN, LOW) right after setting the pin mode, so the LED starts off. (too\_slow.ino:8) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | Each confirmed press flips ledOn and writes it to LED\_BUILTIN (lines 16-17), and the code waits for release before it can detect another press, so successive presses alternate the LED state correctly. (too\_slow.ino:16) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | FAIL | The LED is only updated after a blocking delay(35) used for debouncing, so the LED change lags the physical press by at least 35 ms, exceeding the 20 ms requirement for an unnoticeable delay. (too\_slow.ino:14) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | The code validates a LOW reading with a 35 ms delay-and-recheck before toggling (lines 13-16), and then blocks until release (line 19), so a single physical press (with typical sub-35ms bounce) produces exactly one toggle. (too\_slow.ino:13) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | PASS | On every confirmed toggle, Serial1.println(ledOn ? "ON" : "OFF") prints the new state on its own line. (too\_slow.ino:18) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | The sketch initializes and uses Serial1 (not Serial) with Serial1.begin(9600) and Serial1.println, matching the required port and baud rate. (too\_slow.ino:9) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | pinMode(2, INPUT\_PULLUP) configures digital pin 2 (D2) with the internal pull-up as required. (too\_slow.ino:6) |
