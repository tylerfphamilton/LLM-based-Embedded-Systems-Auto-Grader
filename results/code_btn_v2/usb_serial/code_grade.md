# Code-only grade: usb_serial

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | setup() calls digitalWrite(led, LOW) right after pinMode(led, OUTPUT); on Nano 33 BLE the single orange LED\_BUILTIN (D13) is active-high (unlike the RGB LED), so LOW keeps it off at reset. (usb\_serial.ino:13-14) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | isOn starts false; on each debounced falling edge (raw == LOW) isOn is flipped and written to the LED, so the first press turns it on (HIGH) and the next press turns it off (LOW), toggling on presses only (not releases). (usb\_serial.ino:24-29) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | digitalWrite(led, isOn) is executed immediately once the 5ms debounce window elapses, inside a tight non-blocking loop with no delay(), so the LED updates well within 20ms of the stabilized press. (usb\_serial.ino:24-29) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | The code tracks the last raw reading and only commits a new stable state (and toggles) after the raw value has been constant for 5ms (millis() - rawChangedMs \>= 5), a standard non-blocking debounce pattern that collapses bounce into a single stable transition. (usb\_serial.ino:19-30) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | FAIL | The ON/OFF message is printed via Serial.println (the USB CDC serial port), not Serial1, so the required hardware-UART message on Serial1 is never sent. (usb\_serial.ino:29) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | FAIL | Serial1 is never referenced anywhere in the sketch; only Serial.begin(9600) and Serial.println are used, which is the USB serial port, contradicting the requirement to use Serial1 (D0/D1). (usb\_serial.ino:15) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | pinMode(button, INPUT\_PULLUP) is called in setup() with button defined as pin 2, matching the required configuration. (usb\_serial.ino:3,12) |
