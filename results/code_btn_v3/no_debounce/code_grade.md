# Code-only grade: no_debounce

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | setup() explicitly sets LED\_BUILTIN as OUTPUT and writes LOW before any interrupt can fire, so the LED starts off. (no\_debounce.ino:14-15) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | buttonPressed() flips ledState and writes it to LED\_BUILTIN on every FALLING interrupt, so logically each press toggles the LED on then off alternately. (no\_debounce.ino:6-9) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The LED is toggled directly inside the hardware interrupt service routine buttonPressed(), which executes essentially immediately on the falling edge, well under 20 ms. (no\_debounce.ino:6-9) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | FAIL | There is no debouncing logic anywhere: attachInterrupt fires on every FALLING edge and buttonPressed() toggles unconditionally, so mechanical bounce will cause multiple spurious toggles per physical press. (no\_debounce.ino:17) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | PASS | loop() checks the changed flag set by the ISR and prints 'ON' or 'OFF' via Serial1.println based on the new ledState, each on its own line. (no\_debounce.ino:21-23) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | Serial1.begin(9600) is used for initialization and Serial1.println for output; the USB Serial object is never used. (no\_debounce.ino:16) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | setup() configures pin 2 as INPUT\_PULLUP, matching the button wiring without an external resistor. (no\_debounce.ino:13) |
