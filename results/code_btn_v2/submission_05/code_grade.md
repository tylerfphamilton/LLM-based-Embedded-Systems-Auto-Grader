# Code-only grade: submission_05

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | setup() explicitly calls digitalWrite(kLed, LOW) right after configuring the pin as OUTPUT, and ledOn is initialized to false, so the LED is off immediately after reset. (submission\_05.ino:24-25) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | When the input settles to a new stable value and that value is LOW, ledOn is flipped and written to the LED pin, so each detected press toggles the LED on then off alternately. (submission\_05.ino:40-45) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The toggle happens as soon as kDebounce (5 microseconds) elapses after the input stops changing, which is far under the 20 ms threshold, and there are no blocking delays in loop(). (submission\_05.ino:40-45) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | FAIL | kDebounce is 5, but the timestamps come from micros(), so the debounce window is only 5 microseconds, not 5 milliseconds. Real switch bounce typically lasts several milliseconds, so this window is far too short to filter it, and a single physical press will likely cause multiple rapid toggles. (submission\_05.ino:15,31,40) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | PASS | On every detected LOW transition the code calls Serial1.println(ledOn ? "ON" : "OFF"), printing the new state on its own line. (submission\_05.ino:45) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | The code calls Serial1.begin(9600) in setup and Serial1.println(...) for state messages, never using the USB Serial object. (submission\_05.ino:26) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | pinMode(kButton, INPUT\_PULLUP) is called with kButton = 2, matching the requirement to use the internal pull-up on D2. (submission\_05.ino:13,23) |
