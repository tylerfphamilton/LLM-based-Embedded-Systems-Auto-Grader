# Code-only grade: correct_alt_style

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | setup() calls digitalWrite(LED\_BUILTIN, LOW) right after pinMode, ensuring LED is off at startup. (correct\_alt\_style.ino:25) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | The state machine toggles \`led\` and writes it to LED\_BUILTIN exactly once when transitioning from MAYBE\_PRESSED to PRESSED, i.e. once per debounced press, so each press flips the LED. (correct\_alt\_style.ino:40-44) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The LED is updated after only a 10 ms debounce confirmation delay (non-blocking, via millis()), well under the 20 ms threshold, and loop() has no other blocking delays. (correct\_alt\_style.ino:40-44) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | The 4-state machine (RELEASED/MAYBE\_PRESSED/PRESSED/MAYBE\_RELEASED) only commits to PRESSED (and toggles the LED) after the input stays LOW for 10 ms, and reverts to RELEASED on bounce back to HIGH before that, so bouncing cannot cause multiple toggles for one physical press. (correct\_alt\_style.ino:37-46) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | PASS | report() prints "ON\\n" or "OFF\\n" via Serial1.print based on the new \`led\` value, called right after each toggle, producing the new state on its own line. (correct\_alt\_style.ino:14-20,44) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | Serial1.begin(9600) is used in setup and Serial1.print in report(); the USB Serial object is never referenced. (correct\_alt\_style.ino:26) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | BTN is defined as 2 and pinMode(BTN, INPUT\_PULLUP) is called in setup(), matching the required pull-up configuration on D2. (correct\_alt\_style.ino:6,23) |
