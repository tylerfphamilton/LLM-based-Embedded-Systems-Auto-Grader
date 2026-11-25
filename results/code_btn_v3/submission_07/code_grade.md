# Code-only grade: submission_07

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | setup() calls digitalWrite(ledPin, LOW) right after pinMode, so the LED is explicitly off after reset. (submission\_07.ino:22) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | On each accepted falling edge (prev==HIGH && cur==LOW) the code flips the ledOn boolean and writes it to the LED pin, giving alternating ON/OFF behaviour per press. (submission\_07.ino:30-33) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The LED is written to immediately in the same loop iteration that detects the falling edge, with no delay() calls anywhere, so reaction is effectively instantaneous (well under 20 ms). (submission\_07.ino:30-33) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | After an accepted press, further HIGH-\>LOW transitions are ignored for HOLDOFF\_MS (30 ms) via the millis()-based check, so bounce edges occurring in that window do not cause extra toggles. (submission\_07.ino:31) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | PASS | Immediately after toggling, Serial1.println(ledOn ? "ON" : "OFF") prints the new state on its own line. (submission\_07.ino:34) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | Serial1.begin(9600) is used in setup and Serial1.println is used for output; the USB Serial object is never referenced. (submission\_07.ino:23) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | pinMode(buttonPin, INPUT\_PULLUP) is called with buttonPin = 2, matching the hardware setup with no external resistor. (submission\_07.ino:20) |
