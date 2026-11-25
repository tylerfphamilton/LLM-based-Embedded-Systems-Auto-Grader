# Code-only grade: wrong_baud

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | In setup(), pinMode(LED, OUTPUT) is followed by digitalWrite(LED, LOW), explicitly turning the LED off at startup before any button logic runs. (wrong\_baud.ino:14-15) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | Each valid press flips lightOn with lightOn = !lightOn and writes it to LED; starting from lightOn=false, the first toggle turns it ON, the next turns it OFF, alternating correctly. (wrong\_baud.ino:32-33) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The loop has no blocking delay() and toggles the LED as soon as the 5 ms debounce window (DEBOUNCE\_TIME) elapses, well under the 20 ms threshold. (wrong\_baud.ino:30-33) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | FAIL | DEBOUNCE\_TIME is only 5 ms; any bounce (brief HIGH read) resets wasPressed to false, and if the signal returns LOW afterward it is treated as a brand-new press, restarting pressStart and potentially re-triggering the toggle. Real switch bounce often lasts longer than 5 ms, so this window is too short to guarantee exactly one toggle per physical press. (wrong\_baud.ino:22-26) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | FAIL | The code does print 'ON'/'OFF' on toggle via Serial1.println, but Serial1 is initialized with Serial1.begin(115200), not the required 9600 baud, so the state messages are sent at the wrong baud rate. (wrong\_baud.ino:16) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | FAIL | The code correctly uses Serial1 (not USB Serial) for output, but it is configured with Serial1.begin(115200) instead of the required 9600 baud. (wrong\_baud.ino:16) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | BUTTON is defined as pin 2 and pinMode(BUTTON, INPUT\_PULLUP) is called in setup(), correctly configuring D2 with the internal pull-up. (wrong\_baud.ino:3,13) |
