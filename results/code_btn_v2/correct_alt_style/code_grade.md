# Code-only grade: correct_alt_style

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | setup() explicitly calls digitalWrite(LED\_BUILTIN, LOW) and initializes led=false, so the LED starts off after reset. (correct\_alt\_style.ino:25) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | The state machine transitions from MAYBE\_PRESSED to PRESSED only once per press, toggling led = !led each time, so successive presses alternate the LED on/off. (correct\_alt\_style.ino:40-45) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The LED is updated as soon as the 10ms debounce window for the press confirms, well under the 20ms threshold, and loop() runs continuously without blocking delays. (correct\_alt\_style.ino:40-44) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | The four-state machine (RELEASED/MAYBE\_PRESSED/PRESSED/MAYBE\_RELEASED) requires the input to stay stable for 10ms before confirming a press or release, filtering out bounce so only one toggle occurs per physical press. (correct\_alt\_style.ino:33-57) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | PASS | report() prints "ON\\n" or "OFF\\n" over Serial1 each time the LED state toggles, producing the new state on its own line. (correct\_alt\_style.ino:14-20) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | Serial1.begin(9600) is called in setup and all status output uses Serial1; the USB Serial object is never used. (correct\_alt\_style.ino:26) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | pinMode(BTN, INPUT\_PULLUP) is called with BTN defined as pin 2, matching the required configuration. (correct\_alt\_style.ino:23) |
