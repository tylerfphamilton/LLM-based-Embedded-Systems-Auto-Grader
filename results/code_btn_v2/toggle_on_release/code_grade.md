# Code-only grade: toggle_on_release

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | setup() sets LED\_BUILTIN as OUTPUT and immediately calls digitalWrite(LED\_BUILTIN, LOW), so the LED starts off after reset. (toggle\_on\_release.ino:14-15) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | Each full press/release cycle (LOW then back to HIGH) results in exactly one toggle of the \`on\` boolean and corresponding digitalWrite, so successive presses alternate the LED state in order. (toggle\_on\_release.ino:27-30) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | FAIL | The toggle only fires when the debounced signal becomes HIGH again, i.e. on button release (line 27), not on the initial press. The delay between the actual press and the LED change therefore equals however long the user holds the button down, which is not bounded by 20 ms as required. (toggle\_on\_release.ino:20-30) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | FAIL | The debounce window DEBOUNCE is only 5 ms (line 5), which is shorter than typical mechanical contact bounce (often 10-50 ms for the kind of tactile pushbuttons used in this lab). A bounce lasting longer than 5 ms can cause the stable value to be updated prematurely, producing more than one toggle per physical press. (toggle\_on\_release.ino:5) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | PASS | Immediately after toggling \`on\`, the code calls Serial1.println(on ? "ON" : "OFF"), printing the new state on its own line each time a toggle occurs. (toggle\_on\_release.ino:30) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | Serial1.begin(9600) is called in setup and Serial1.println is used for output; the USB Serial object is never referenced. (toggle\_on\_release.ino:16) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | BTN\_PIN is defined as 2 and pinMode(BTN\_PIN, INPUT\_PULLUP) is called in setup, matching the required pull-up configuration on D2. (toggle\_on\_release.ino:4,13) |
