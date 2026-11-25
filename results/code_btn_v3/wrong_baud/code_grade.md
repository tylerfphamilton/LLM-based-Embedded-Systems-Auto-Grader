# Code-only grade: wrong_baud

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | In setup(), pinMode(LED, OUTPUT) is followed immediately by digitalWrite(LED, LOW), so the LED starts off after reset. (wrong\_baud.ino:14-15) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | When a debounced press is detected (pressed && !counted && elapsed \>= DEBOUNCE\_TIME), lightOn is flipped with lightOn = !lightOn and written to the LED, so successive presses alternate the LED state correctly. (wrong\_baud.ino:30-34) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The toggle fires DEBOUNCE\_TIME (5 ms) after the button is detected pressed, and digitalWrite happens immediately in the same loop iteration, well under the 20 ms threshold. (wrong\_baud.ino:5,30-33) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | A 'counted' latch prevents re-toggling while the button stays pressed after the first confirmed debounce (counted=true until release sets it false again), so one physical press produces one toggle; the press-start time is re-armed only on a fresh LOW transition, filtering bounce before the debounce window elapses. (wrong\_baud.ino:22-35) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | FAIL | Serial1.println(lightOn ? "ON" : "OFF") does print the new state on its own line on every toggle, but the port is opened with Serial1.begin(115200) instead of the required 9600 baud, so the requirement (which specifies 9600 baud) is not met. (wrong\_baud.ino:16) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | FAIL | The code correctly uses Serial1 (not the USB Serial object), but it calls Serial1.begin(115200) rather than Serial1.begin(9600), so Serial1 is not configured at the required 9600 baud. (wrong\_baud.ino:16) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | BUTTON is defined as 2 and pinMode(BUTTON, INPUT\_PULLUP) is called in setup(), correctly configuring D2 with the internal pull-up. (wrong\_baud.ino:3,13) |
