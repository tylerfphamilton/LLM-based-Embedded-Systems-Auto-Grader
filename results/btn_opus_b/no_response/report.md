# Autograder report: button_toggle_opus_b

**Submission:** `no_response`  
**Result: 7 of 16 checks passed** · 9 failed · 0 borderline · 0 could not be measured

> Debounced button toggle: button on D2 (active low, INPUT_PULLUP) toggles the LED on D13 once per bouncy press and prints ON/OFF on Serial1 at 9600 baud.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The LED is off after reset. | `final_level` | = 0 | 0 | ✅ PASS |
| The LED is off after reset. | `edge_count` | = 0 | 0 | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `delay_ms` | any value (not null) | no value (null) | ❌ FAIL |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | no value (null) | ❌ FAIL |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `to_edge_count` | = 1 | 0 | ❌ FAIL |
| The first press prints ON on its own line on Serial1. | `text` | matches /^ON\\r?\\n$/ | "" | ❌ FAIL |
| The first press prints ON on its own line on Serial1. | `framing_errors` | = 0 | 0 | ✅ PASS |
| Releasing the button does not change the LED (it stays on). | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button does not change the LED (it stays on). | `final_level` | = 1 | 0 | ❌ FAIL |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | any value (not null) | no value (null) | ❌ FAIL |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | no value (null) | ❌ FAIL |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `to_edge_count` | = 1 | 0 | ❌ FAIL |
| The second press prints OFF on its own line on Serial1. | `text` | matches /^OFF\\r?\\n$/ | "" | ❌ FAIL |
| The second press prints OFF on its own line on Serial1. | `framing_errors` | = 0 | 0 | ✅ PASS |
| Releasing the button again leaves the LED off. | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button again leaves the LED off. | `final_level` | = 0 | 0 | ✅ PASS |

## What to fix

### ❌ The first bouncy press turns the LED on exactly once, within 100 ms. (`delay_ms`)

- **Why:** measured no value (null), but expected any value (not null)
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: button read from the wrong pin (D3 instead of D2) means the LED never toggles, so no edge/delay is produced.
- **Where to look:** no\_response.ino:3

### ❌ The first bouncy press turns the LED on exactly once, within 100 ms. (`delay_ms`)

- **Why:** nothing was measured for 'delay\_ms' (null, e.g. no signal or no response); expected ≤ 100 ms
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: button read from the wrong pin (D3 instead of D2) prevents any LED transition within the 100 ms window.
- **Where to look:** no\_response.ino:3

### ❌ The first bouncy press turns the LED on exactly once, within 100 ms. (`to_edge_count`)

- **Why:** measured 0, but expected = 1
- **Feedback:** The button input is wired to D2 per the assignment, but the code defines \`const int buttonPin = 3;\` on line 3 and calls \`digitalRead(buttonPin)\` on that wrong pin. Since pin 3 never sees the simulated button presses, \`reading\` never changes from HIGH, so the toggle logic in loop() never executes and the LED never turns on. Check the pin number constant against the required D2 wiring.
- **Where to look:** no\_response.ino:3

### ❌ The first press prints ON on its own line on Serial1. (`text`)

- **Why:** received "", but expected matches /^ON\\r?\\n$/
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: because buttonState never changes (button polled on D3 instead of D2), the \`Serial1.println("ON")\` branch on line 33 is never reached, so nothing is printed.
- **Where to look:** no\_response.ino:3

### ❌ Releasing the button does not change the LED (it stays on). (`final_level`)

- **Why:** measured 0, but expected = 1
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: since the LED was never turned on in the first place (button polled on the wrong pin), it reads back as LOW instead of staying HIGH through the release.
- **Where to look:** no\_response.ino:3

### ❌ The second bouncy press turns the LED off exactly once, within 100 ms. (`delay_ms`)

- **Why:** measured no value (null), but expected any value (not null)
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: the button pin mismatch (D3 vs required D2) means the second press is never detected either, so the LED never turns off.
- **Where to look:** no\_response.ino:3

### ❌ The second bouncy press turns the LED off exactly once, within 100 ms. (`delay_ms`)

- **Why:** nothing was measured for 'delay\_ms' (null, e.g. no signal or no response); expected ≤ 100 ms
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: wrong button pin means no transition occurs within the 100 ms window for the second press either.
- **Where to look:** no\_response.ino:3

### ❌ The second bouncy press turns the LED off exactly once, within 100 ms. (`to_edge_count`)

- **Why:** measured 0, but expected = 1
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: the second press is also never seen because the code polls D3 instead of D2, so the LED-off edge never occurs.
- **Where to look:** no\_response.ino:3

### ❌ The second press prints OFF on its own line on Serial1. (`text`)

- **Why:** received "", but expected matches /^OFF\\r?\\n$/
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: with buttonState never updating (wrong pin), the \`Serial1.println("OFF")\` branch on line 35 is never executed.
- **Where to look:** no\_response.ino:3

## Not graded automatically

- **Implement debouncing in software, without blocking delay() calls.**: The pins can't show how the debouncing is done. Only its effect (one toggle per press, fast response) is tested.
- **Comment your code.**: Code style can't be observed electrically.

## Assumptions the grader made

- The handout gives no number for 'quickly', so the LED must change within 100 ms of the first press edge, which is about where people start to notice a delay.
- A bouncy press is 5 edges 200 us apart, ending LOW (pressed).
- Releasing the button is the board letting go of D2, so the student's INPUT\_PULLUP pulls it high.
- Serial lines may end with \\n or \\r\\n.
- Releasing the button must not toggle the LED (only presses do).
