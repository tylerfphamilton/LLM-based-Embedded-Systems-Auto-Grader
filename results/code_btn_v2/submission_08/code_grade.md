# Code-only grade: submission_08

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | setup() sets LED\_PIN to OUTPUT and immediately writes LOW to it before Serial1 is even started, so the LED is off right after reset. (submission\_08.ino:21-22) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | When a stable LOW sample is detected (btnState transitions to LOW) the code flips the 'lit' boolean and writes it to LED\_PIN, so successive presses alternate the LED on/off. (submission\_08.ino:35-39) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The loop has no blocking delay() and only waits DEBOUNCE\_MS (5 ms) of stability before updating the LED, well under the 20 ms perceptibility threshold. (submission\_08.ino:10,35) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | The code only accepts a new button state once the raw sample has remained unchanged for DEBOUNCE\_MS (5 ms), and only toggles when btnState actually changes, so bouncing during that window does not produce multiple toggles. (submission\_08.ino:30-41) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | PASS | Immediately after each toggle, Serial1.println(lit ? "ON" : "OFF") prints the new state on its own line. (submission\_08.ino:40) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | The sketch calls Serial1.begin(9600) in setup and uses Serial1.println for output, never the USB Serial object. (submission\_08.ino:24,40) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | FAIL | The requirement calls for pinMode(BTN\_PIN, INPUT\_PULLUP), but the code instead uses pinMode(BTN\_PIN, INPUT) followed by digitalWrite(BTN\_PIN, HIGH), an old AVR-style trick rather than the required INPUT\_PULLUP configuration. (submission\_08.ino:18-19) |
