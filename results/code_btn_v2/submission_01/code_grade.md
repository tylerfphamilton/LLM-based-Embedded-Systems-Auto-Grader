# Code-only grade: submission_01

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | setup() sets LED\_PIN as OUTPUT and immediately calls digitalWrite(LED\_PIN, LOW), and ledOn is initialized false, so the LED starts off after reset. (submission\_01.ino:17-18) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | On each debounced LOW transition the code flips ledOn and writes it to LED\_PIN, so successive presses alternate the LED between on and off. (submission\_01.ino:35-38) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The loop has no blocking delay() and the debounce window is only 5 ms (DEBOUNCE\_MS), so the LED updates well within 20 ms of a stable press. (submission\_01.ino:8,32-38) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | The code implements a standard non-blocking debounce: any raw change resets a timer, and the debounced value (and the toggle action) is only updated once the input has been stable for DEBOUNCE\_MS, so bounce does not cause multiple toggles. (submission\_01.ino:26-39) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | FAIL | On a toggle the code prints ledOn ? "ON" : "OFF" (line 36) before ledOn is flipped on line 37, so it always prints the OLD state rather than the new state after the toggle (e.g. the very first press prints "OFF" while turning the LED ON). (submission\_01.ino:36-37) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | The code calls Serial1.begin(9600) in setup and Serial1.println(...) to report state, never using the USB Serial object. (submission\_01.ino:19,36) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | BUTTON\_PIN is defined as 2 and configured with pinMode(BUTTON\_PIN, INPUT\_PULLUP) in setup(). (submission\_01.ino:6,16) |
