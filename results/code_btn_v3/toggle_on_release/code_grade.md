# Code-only grade: toggle_on_release

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | In setup(), digitalWrite(LED\_BUILTIN, LOW) is called right after pinMode(LED\_BUILTIN, OUTPUT), before any other logic runs, guaranteeing the LED starts off. (toggle\_on\_release.ino:14-15) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | The debounced state machine toggles the \`on\` boolean and writes it to LED\_BUILTIN only when the debounced state becomes HIGH (button released after a press), so each full press/release cycle flips the LED exactly once, alternating ON/OFF starting from off. (toggle\_on\_release.ino:25-31) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The debounce window is only DEBOUNCE=5ms, and the toggle/digitalWrite happen as soon as that short stability window elapses after release, well under the 20ms threshold, with no blocking delay() in loop(). (toggle\_on\_release.ino:5,25-30) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | Every raw change resets changedAt (line 22), and the stable state/toggle is only updated once the signal has stayed constant for more than DEBOUNCE ms (line 25); any bouncing before that window keeps resetting the timer, so a single physical press can only produce one toggle regardless of how long the bounce lasts. (toggle\_on\_release.ino:20-31) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | PASS | On each accepted toggle, Serial1.println(on ? "ON" : "OFF") prints the new state on its own line. (toggle\_on\_release.ino:30) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | Serial1.begin(9600) is used in setup() and Serial1.println is used for output; the USB Serial object is never referenced. (toggle\_on\_release.ino:16,30) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | BTN\_PIN is defined as 2 and configured with pinMode(BTN\_PIN, INPUT\_PULLUP) in setup(). (toggle\_on\_release.ino:4,13) |
