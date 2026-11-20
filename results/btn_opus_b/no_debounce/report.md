# Autograder report: button_toggle_opus_b

**Submission:** `no_debounce`  
**Result: 12 of 16 checks passed** · 4 failed · 0 borderline · 0 could not be measured

> Debounced button toggle: button on D2 (active low, INPUT_PULLUP) toggles the LED on D13 once per bouncy press and prints ON/OFF on Serial1 at 9600 baud.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The LED is off after reset. | `final_level` | = 0 | 0 | ✅ PASS |
| The LED is off after reset. | `edge_count` | = 0 | 0 | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `delay_ms` | any value (not null) | 0.011 ms | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | 0.011 ms | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `to_edge_count` | = 1 | 3 | ❌ FAIL |
| The first press prints ON on its own line on Serial1. | `text` | matches /^ON\\r?\\n$/ | "ON\\r\\nON\\r\\n" | ❌ FAIL |
| The first press prints ON on its own line on Serial1. | `framing_errors` | = 0 | 0 | ✅ PASS |
| Releasing the button does not change the LED (it stays on). | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button does not change the LED (it stays on). | `final_level` | = 1 | 1 | ✅ PASS |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | any value (not null) | 0.011 ms | ✅ PASS |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | 0.011 ms | ✅ PASS |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `to_edge_count` | = 1 | 3 | ❌ FAIL |
| The second press prints OFF on its own line on Serial1. | `text` | matches /^OFF\\r?\\n$/ | "OFF\\r\\nOFF\\r\\n" | ❌ FAIL |
| The second press prints OFF on its own line on Serial1. | `framing_errors` | = 0 | 0 | ✅ PASS |
| Releasing the button again leaves the LED off. | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button again leaves the LED off. | `final_level` | = 0 | 0 | ✅ PASS |

## What to fix

### ❌ The first bouncy press turns the LED on exactly once, within 100 ms. (`to_edge_count`)

- **Why:** measured 3, but expected = 1
- **Feedback:** The ISR buttonPressed() (no\_debounce.ino:6-10) toggles the LED on every FALLING edge with no debounce logic, so a single bouncy press (which generates multiple falling edges) toggles the LED 3 times instead of once. Add a debounce timer (e.g. ignore edges within a few ms using millis()) inside or around the ISR.
- **Where to look:** no\_debounce.ino:6

### ❌ The first press prints ON on its own line on Serial1. (`text`)

- **Why:** received "ON\\r\\nON\\r\\n", but expected matches /^ON\\r?\\n$/
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same bounce-triggered multiple toggles cause buttonPressed() to set changed=true multiple times, so loop() prints "ON" twice instead of once.
- **Where to look:** no\_debounce.ino:21

### ❌ The second bouncy press turns the LED off exactly once, within 100 ms. (`to_edge_count`)

- **Why:** measured 3, but expected = 1
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same lack of debounce in buttonPressed() causes the second bouncy press to also register 3 toggles instead of 1.
- **Where to look:** no\_debounce.ino:6

### ❌ The second press prints OFF on its own line on Serial1. (`text`)

- **Why:** received "OFF\\r\\nOFF\\r\\n", but expected matches /^OFF\\r?\\n$/
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same bounce issue causes "OFF" to be printed twice for the second press.
- **Where to look:** no\_debounce.ino:21

## Not graded automatically

- **Implement debouncing in software, without blocking delay() calls.**: The pins can't show how the debouncing is done. Only its effect (one toggle per press, fast response) is tested.
- **Comment your code.**: Code style can't be observed electrically.

## Assumptions the grader made

- The handout gives no number for 'quickly', so the LED must change within 100 ms of the first press edge, which is about where people start to notice a delay.
- A bouncy press is 5 edges 200 us apart, ending LOW (pressed).
- Releasing the button is the board letting go of D2, so the student's INPUT\_PULLUP pulls it high.
- Serial lines may end with \\n or \\r\\n.
- Releasing the button must not toggle the LED (only presses do).
