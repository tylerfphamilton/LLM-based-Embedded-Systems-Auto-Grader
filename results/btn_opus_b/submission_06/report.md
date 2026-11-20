# Autograder report: button_toggle_opus_b

**Submission:** `submission_06`  
**Result: 11 of 16 checks passed** · 5 failed · 0 borderline · 0 could not be measured

> Debounced button toggle: button on D2 (active low, INPUT_PULLUP) toggles the LED on D13 once per bouncy press and prints ON/OFF on Serial1 at 9600 baud.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The LED is off after reset. | `final_level` | = 0 | 0 | ✅ PASS |
| The LED is off after reset. | `edge_count` | = 0 | 0 | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `delay_ms` | any value (not null) | 0.013 ms | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | 0.013 ms | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `to_edge_count` | = 1 | 3 | ❌ FAIL |
| The first press prints ON on its own line on Serial1. | `text` | matches /^ON\\r?\\n$/ | "ON\\r\\nOFF\\r\\nON\\r\\n" | ❌ FAIL |
| The first press prints ON on its own line on Serial1. | `framing_errors` | = 0 | 0 | ✅ PASS |
| Releasing the button does not change the LED (it stays on). | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button does not change the LED (it stays on). | `final_level` | = 1 | 0 | ❌ FAIL |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | any value (not null) | 0.012 ms | ✅ PASS |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | 0.012 ms | ✅ PASS |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `to_edge_count` | = 1 | 3 | ❌ FAIL |
| The second press prints OFF on its own line on Serial1. | `text` | matches /^OFF\\r?\\n$/ | "ON\\r\\nOFF\\r\\nON\\r\\n" | ❌ FAIL |
| The second press prints OFF on its own line on Serial1. | `framing_errors` | = 0 | 0 | ✅ PASS |
| Releasing the button again leaves the LED off. | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button again leaves the LED off. | `final_level` | = 0 | 0 | ✅ PASS |

## What to fix

### ❌ The first bouncy press turns the LED on exactly once, within 100 ms. (`to_edge_count`)

- **Why:** measured 3, but expected = 1
- **Feedback:** The debounce logic in loop() (sketch.ino:27) only blocks re-toggling for LOCKOUT\_MS=200ms after the last toggle, but it never waits for the button to actually go HIGH (released) again. Since the simulated bouncy press keeps BUTTON\_PIN LOW for longer than 200ms, once the lockout window expires the condition on line 27 is true again (still LOW), so the LED toggles a second and third time (ON-\>OFF-\>ON) during what should be a single press. Fix by requiring a release (or a stable LOW read over a short debounce interval) before allowing the next toggle, rather than just waiting out a fixed lockout timer.
- **Where to look:** sketch.ino:27

### ❌ The first press prints ON on its own line on Serial1. (`text`)

- **Why:** received "ON\\r\\nOFF\\r\\nON\\r\\n", but expected matches /^ON\\r?\\n$/
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same lockout-without-release bug causes three toggles (and three prints: ON, OFF, ON) instead of one ON print for the first press.
- **Where to look:** sketch.ino:27

### ❌ Releasing the button does not change the LED (it stays on). (`final_level`)

- **Why:** measured 0, but expected = 1
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Because the first press already toggles the LED three times instead of once (ON-\>OFF-\>ON), the LED's final level after that press/release sequence ends up OFF (0) instead of the expected ON (1); this is a downstream effect of the same lockout timing bug.
- **Where to look:** sketch.ino:27

### ❌ The second bouncy press turns the LED off exactly once, within 100 ms. (`to_edge_count`)

- **Why:** measured 3, but expected = 1
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). The same lockout-without-release bug repeats on the second bouncy press, producing three toggles instead of one.
- **Where to look:** sketch.ino:27

### ❌ The second press prints OFF on its own line on Serial1. (`text`)

- **Why:** received "ON\\r\\nOFF\\r\\nON\\r\\n", but expected matches /^OFF\\r?\\n$/
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). The same bug causes the second press to print ON, OFF, ON instead of a single OFF line.
- **Where to look:** sketch.ino:27

## Not graded automatically

- **Implement debouncing in software, without blocking delay() calls.**: The pins can't show how the debouncing is done. Only its effect (one toggle per press, fast response) is tested.
- **Comment your code.**: Code style can't be observed electrically.

## Assumptions the grader made

- The handout gives no number for 'quickly', so the LED must change within 100 ms of the first press edge, which is about where people start to notice a delay.
- A bouncy press is 5 edges 200 us apart, ending LOW (pressed).
- Releasing the button is the board letting go of D2, so the student's INPUT\_PULLUP pulls it high.
- Serial lines may end with \\n or \\r\\n.
- Releasing the button must not toggle the LED (only presses do).
