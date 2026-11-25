# Code-only grade: submission_01

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | In setup(), pinMode(LED\_PIN, OUTPUT) is followed by digitalWrite(LED\_PIN, LOW) before any button handling, so the LED starts off after reset. (submission\_01.ino:17-18) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | On each accepted falling edge (debounced == LOW), ledOn is flipped and digitalWrite reflects the new ledOn value, so consecutive presses alternately turn the LED on and off. (submission\_01.ino:35-38) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | DEBOUNCE\_MS is set to 5 ms and the loop has no blocking delays, so the LED updates well within 20 ms of a stable press being detected. (submission\_01.ino:8,22-40) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | The code resets lastEdgeMs on every raw change and only commits a new debounced state (and toggles) once the raw level has been stable for DEBOUNCE\_MS, and only toggles when debounced transitions to LOW, which prevents multiple toggles from contact bounce. (submission\_01.ino:26-39) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | FAIL | The print happens before ledOn is updated, so it prints the OLD LED state (e.g., prints "OFF" right when the LED is about to turn ON), not the new state as required. (submission\_01.ino:36-38) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | The code calls Serial1.begin(9600) in setup and Serial1.println(...) for the state messages, using the UART Serial1 object rather than the USB Serial port. (submission\_01.ino:19,36) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | pinMode(BUTTON\_PIN, INPUT\_PULLUP) is called in setup with BUTTON\_PIN defined as pin 2, matching the required D2 pull-up configuration. (submission\_01.ino:6,16) |
