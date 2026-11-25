# Code-only grade: submission_09

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | In setup(), digitalWrite(LED\_PIN, LOW) explicitly turns the LED off right after pinMode is set, and the ledOn flag is initialized to false, so the LED is off immediately after reset. (submission\_09.ino:23) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | When a debounced transition to LOW (pressed) is detected, ledOn is flipped with ledOn = !ledOn, and the LED is driven from ledOn every loop, so successive presses alternately turn it on and off. (submission\_09.ino:38-39) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | loop() has no delay() calls and runs continuously; the debounce window is only 5 ms (DEBOUNCE\_MS), so the LED output is updated well within 20 ms of a stable press. (submission\_09.ino:13,36) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | The code tracks the last raw change time (rawChangeMs) and only commits a new debouncedLast/toggle once the raw signal has been stable for DEBOUNCE\_MS; since debouncedLast is updated to match raw after each commit, bouncing before the stable window elapses does not cause repeated toggles, giving exactly one toggle per physical press. (submission\_09.ino:30-41) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | FAIL | Serial1.println(ledOn ? "ON" : "OFF") is called unconditionally on every pass through loop(), not just when a toggle occurs, so it floods Serial1 with the current state continuously instead of printing once per toggle. (submission\_09.ino:45) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | The sketch calls Serial1.begin(9600) in setup() and Serial1.println() in loop(), using the UART Serial1 object at the required baud rate rather than the USB Serial. (submission\_09.ino:24,45) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | PIN\_BUTTON is defined as 2 and pinMode(PIN\_BUTTON, INPUT\_PULLUP) configures it with the internal pull-up as required. (submission\_09.ino:11,21) |
