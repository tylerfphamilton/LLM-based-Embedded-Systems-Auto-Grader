# Code-only grade: submission_02

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | setup() sets pinMode(LED\_BUILTIN, OUTPUT) then immediately calls digitalWrite(LED\_BUILTIN, LOW), so the LED is off right after reset. (submission\_02.ino:32-33) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | PASS | When the debounced level transitions to LOW (pressed), ledState is flipped with !ledState and written to LED\_BUILTIN, so successive presses alternate the LED between on and off. (submission\_02.ino:46-52) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The loop has no blocking delay() and the debounce window is only DEBOUNCE\_TIME = 8 ms, so the LED updates well under the 20 ms threshold after the button settles. (submission\_02.ino:14,45-52) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | PASS | The code restarts changeTime on every raw level change (line 41) and only commits a state change once the level has been stable for DEBOUNCE\_TIME ms (line 45-47), which is the standard software-debounce pattern that filters bouncing contacts into a single edge. (submission\_02.ino:40-54) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | FAIL | sendState() uses Serial1.print("ON") / Serial1.print("OFF") without a newline (no println or trailing '\\n'), so consecutive toggle messages are concatenated instead of each appearing on its own line. (submission\_02.ino:22-28) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | The sketch calls Serial1.begin(9600) in setup() and uses Serial1.print(...) in sendState(); the USB Serial object is never used for state output. (submission\_02.ino:34,24-26) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | BUTTON is defined as pin 2 and setup() calls pinMode(BUTTON, INPUT\_PULLUP), configuring D2 with the internal pull-up as required. (submission\_02.ino:13,31) |
