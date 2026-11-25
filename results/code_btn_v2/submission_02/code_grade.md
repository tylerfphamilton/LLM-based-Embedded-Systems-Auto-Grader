# Code-only grade: submission_02

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | In setup(), pinMode(LED\_BUILTIN, OUTPUT) is followed by digitalWrite(LED\_BUILTIN, LOW), so the LED is off immediately after reset. (submission\_02.ino:32-33) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | After debouncing, the code only toggles ledState and writes to LED\_BUILTIN when stableLevel transitions to LOW (pressed), so each discrete press flips the LED state once, alternating on/off. (submission\_02.ino:46-52) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | DEBOUNCE\_TIME is set to 8 ms, so once the button level is stable the LED is updated within 8 ms, well under the 20 ms threshold, and no blocking delay() is used. (submission\_02.ino:14) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | Any change in digitalRead(BUTTON) resets changeTime, and the stableLevel (and the resulting toggle) is only updated once the reading has been constant for DEBOUNCE\_TIME ms, which filters out bounce so a single press yields a single toggle. (submission\_02.ino:40-53) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | FAIL | sendState() uses Serial1.print("ON")/Serial1.print("OFF") without a newline, so consecutive toggle messages are concatenated on a single line instead of each being printed on its own line as required. (submission\_02.ino:22-28) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | The sketch calls Serial1.begin(9600) in setup() and uses Serial1.print() for all state messages, never referencing the USB Serial object. (submission\_02.ino:34) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | BUTTON is defined as pin 2 and pinMode(BUTTON, INPUT\_PULLUP) configures it with the internal pull-up as required. (submission\_02.ino:13,31) |
