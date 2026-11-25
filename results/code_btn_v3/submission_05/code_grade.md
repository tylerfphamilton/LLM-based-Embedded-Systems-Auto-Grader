# Code-only grade: submission_05

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | In setup(), digitalWrite(kLed, LOW) is called right after pinMode(kLed, OUTPUT), so the LED starts off after reset. (submission\_05.ino:24-25) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | When the debounced 'stable' value transitions to LOW, ledOn is flipped with ledOn = !ledOn and written to the LED pin, so each detected press alternates the LED state. (submission\_05.ino:42-44) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The loop is non-blocking and the comparison now - tChange \>= kDebounce (kDebounce=5, compared against micros()) triggers almost immediately after a raw level change settles, well under 20 ms. (submission\_05.ino:40) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | FAIL | kDebounce is set to 5 but is compared against micros() (microsecond resolution), so the effective debounce window is only 5 microseconds, not 5 milliseconds. Real contact bounce typically lasts several milliseconds, so this window is far too short to filter it and a single press could register multiple toggles. (submission\_05.ino:15) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | PASS | Serial1.println(ledOn ? "ON" : "OFF") is called every time the state changes, printing the new state on its own line. (submission\_05.ino:45) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | Serial1.begin(9600) is used in setup and Serial1.println is used for output; the USB Serial object is never referenced. (submission\_05.ino:26) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | pinMode(kButton, INPUT\_PULLUP) is called with kButton = 2, matching the required pull-up configuration on D2. (submission\_05.ino:23) |
