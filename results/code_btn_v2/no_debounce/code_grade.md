# Code-only grade: no_debounce

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | setup() explicitly sets LED\_BUILTIN as OUTPUT and writes LOW before anything else runs, so the LED starts off. (no\_debounce.ino:14-15) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | buttonPressed() flips ledState and writes it to LED\_BUILTIN on each FALLING interrupt from pin 2, so a clean press alternates the LED on/off/on/... (no\_debounce.ino:6-9) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The LED is toggled directly inside the interrupt service routine buttonPressed(), giving essentially immediate (microsecond-scale) reaction to the edge, well under 20 ms. (no\_debounce.ino:6-9) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | FAIL | There is no debouncing logic anywhere (no timestamp check, no state filtering); attachInterrupt(..., FALLING) will fire once per bounce edge, so a single physical press will typically toggle the LED multiple times. (no\_debounce.ino:17) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | PASS | loop() checks the changed flag and prints "ON" or "OFF" via Serial1.println on each toggle detected. (no\_debounce.ino:21-24) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | Serial1.begin(9600) is called in setup and Serial1.println is used for output; the USB Serial object is never referenced. (no\_debounce.ino:16,23) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | pinMode(2, INPUT\_PULLUP) configures the button pin correctly for a switch to GND with no external resistor. (no\_debounce.ino:13) |
