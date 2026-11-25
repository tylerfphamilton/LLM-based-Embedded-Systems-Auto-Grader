# Code-only grade: submission_06

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The on-board LED (pin D13) is off immediately after the board resets or powers up. | PASS | setup() explicitly calls digitalWrite(LED\_PIN, LOW) right after pinMode, so the LED starts off after reset. (submission\_06.ino:21) |
| Each press of the button on pin D2 toggles the LED: the first press turns it on, the next press turns it off, and so on. | FAIL | The loop toggles the LED any time the button reads LOW and at least LOCKOUT\_MS (200ms) has elapsed since the last toggle, regardless of whether the button was released in between. If the user holds the button pressed for more than 200ms (a perfectly normal single press), it will keep toggling the LED repeatedly every 200ms during that one press instead of toggling once per press. (submission\_06.ino:27-32) |
| The LED changes state within 20 ms of a valid button press, so the user notices no delay. | PASS | The LED is updated via digitalWrite on the same iteration the condition becomes true, with no delay() anywhere in loop(), so the reaction is effectively immediate (well under 20ms) once the lockout window has elapsed. (submission\_06.ino:27-30) |
| A single physical button press toggles the LED exactly once, even though the contacts bounce. | FAIL | The 200ms lockout correctly suppresses extra toggles from short contact bounce right after the first LOW reading, but the code never checks for a release before re-arming; if the same physical press stays LOW longer than LOCKOUT\_MS, the condition on line 27 becomes true again and causes additional toggles for what is still a single press. (submission\_06.ino:27-32) |
| On every toggle, the board prints the new LED state, either ON or OFF, on its own line over Serial1 at 9600 baud. | PASS | Serial1.println(led ? "ON" : "OFF") is called on every toggle, printing the new state on its own line. (submission\_06.ino:30) |
| The code uses the Serial1 object (pins D0/D1) configured at 9600 baud for the state messages, not the USB Serial port. | PASS | Serial1.begin(9600) is used in setup and Serial1.println is used for output; the USB Serial object is never used. (submission\_06.ino:22) |
| The code configures pin D2 as INPUT\_PULLUP to read the button, since there is no external resistor. | PASS | pinMode(BUTTON\_PIN, INPUT\_PULLUP) is called with BUTTON\_PIN defined as 2, matching the requirement. (submission\_06.ino:11,19) |
