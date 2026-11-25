# Code-only grade: submission_03

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | setup() calls setLed(false), which writes LED\_OFF (HIGH) to LED\_BUILTIN; since the on-board LED is active-low (as the student's own comment notes), this turns the LED off immediately after reset. (submission\_03.ino:28) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | In loop(), once a reading is debounced and confirmed to be LOW (pressed), isOn is flipped with isOn = !isOn and written via setLed(isOn), so successive presses alternate the LED between on and off. (submission\_03.ino:42-44) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The loop contains no blocking delay(); the LED is updated as soon as the debounce window (DEBOUNCE = 5 ms) elapses after a stable reading, well under the 20 ms threshold. (submission\_03.ino:14,40-44) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | The code tracks raw transitions (lastRead) and only commits a new confirmed state (and toggles) once the reading has been stable for DEBOUNCE ms and differs from the last confirmed state, which is a standard software debounce pattern that produces exactly one toggle per physical press even with contact bounce. (submission\_03.ino:35-47) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | PASS | Immediately after toggling isOn, the code calls Serial1.println(isOn ? "ON" : "OFF"), printing the new state on its own line. (submission\_03.ino:45) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | The sketch initializes and uses Serial1.begin(9600) and Serial1.println(...) exclusively; the USB Serial object is never referenced. (submission\_03.ino:29,45) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | BTN is defined as pin 2 and configured with pinMode(BTN, INPUT\_PULLUP) in setup(), matching the requirement to use the internal pull-up on D2. (submission\_03.ino:8,26) |
