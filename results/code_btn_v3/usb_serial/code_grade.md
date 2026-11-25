# Code-only grade: usb_serial

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | setup() sets pinMode(led, OUTPUT) and immediately calls digitalWrite(led, LOW), turning the LED off right after reset. (usb\_serial.ino:13-14) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | In loop(), when the debounced state settles to LOW (pressed), isOn is flipped and written to the LED, so successive presses alternate it on/off. (usb\_serial.ino:24-29) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The debounce window is only 5 ms (millis() - rawChangedMs \>= 5), and the LED is updated immediately once the stable state is detected, well under 20 ms. (usb\_serial.ino:24-28) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | The code tracks raw changes with a timestamp and only commits a new stable state (and toggles) after it has held for 5 ms without further change, which filters out bounce so one press yields one toggle. (usb\_serial.ino:19-30) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | FAIL | The state is printed with Serial.println, which is the USB CDC serial port, not Serial1 as required; no Serial1 output exists anywhere in the sketch. (usb\_serial.ino:29) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | FAIL | Serial.begin(9600) and Serial.println are used throughout; the Serial1 object (D0/D1) is never referenced, so USB Serial is used instead of Serial1. (usb\_serial.ino:15) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | button is defined as pin 2 and configured with pinMode(button, INPUT\_PULLUP) in setup(). (usb\_serial.ino:3,12) |
