# Code-only grade: submission_03

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | In setup(), setLed(false) is called which writes LED\_OFF (HIGH) to the active-low on-board LED, turning it off at reset. (submission\_03.ino:28) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | When a debounced falling edge is detected (confirmed == LOW), isOn is flipped with isOn = !isOn and applied via setLed(isOn), so successive presses alternate the LED state. (submission\_03.ino:42-44) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The loop has no blocking delay() calls and runs continuously; after the 5 ms debounce window elapses the LED is updated immediately in the same loop iteration, well under 20 ms. (submission\_03.ino:40-44) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | The code tracks raw reads and only commits a new confirmed state after it has been stable for DEBOUNCE (5 ms); it toggles only once per confirmed transition to LOW, correctly filtering contact bounce. (submission\_03.ino:35-46) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | PASS | On every toggle, Serial1.println(isOn ? "ON" : "OFF") prints the new state on its own line. (submission\_03.ino:45) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | Serial1.begin(9600) is used in setup and Serial1.println is used for output, matching the D0/D1 UART at the required baud rate; the USB Serial object is never used. (submission\_03.ino:29) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | pinMode(BTN, INPUT\_PULLUP) is called with BTN defined as pin 2, matching the required wiring with no external resistor. (submission\_03.ino:26) |
