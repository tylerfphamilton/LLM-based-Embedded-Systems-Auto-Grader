# Autograder report: button_toggle_opus_b

**Submission:** `submission_01`  
**Result: 14 of 16 checks passed** · 2 failed · 0 borderline · 0 could not be measured

> Debounced button toggle: button on D2 (active low, INPUT_PULLUP) toggles the LED on D13 once per bouncy press and prints ON/OFF on Serial1 at 9600 baud.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The LED is off after reset. | `final_level` | = 0 | 0 | ✅ PASS |
| The LED is off after reset. | `edge_count` | = 0 | 0 | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `delay_ms` | any value (not null) | 9.324 ms | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | 9.324 ms | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `to_edge_count` | = 1 | 1 | ✅ PASS |
| The first press prints ON on its own line on Serial1. | `text` | matches /^ON\\r?\\n$/ | "OFF\\r\\n" | ❌ FAIL |
| The first press prints ON on its own line on Serial1. | `framing_errors` | = 0 | 0 | ✅ PASS |
| Releasing the button does not change the LED (it stays on). | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button does not change the LED (it stays on). | `final_level` | = 1 | 1 | ✅ PASS |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | any value (not null) | 8.019 ms | ✅ PASS |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | 8.019 ms | ✅ PASS |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `to_edge_count` | = 1 | 1 | ✅ PASS |
| The second press prints OFF on its own line on Serial1. | `text` | matches /^OFF\\r?\\n$/ | "ON\\r\\n" | ❌ FAIL |
| The second press prints OFF on its own line on Serial1. | `framing_errors` | = 0 | 0 | ✅ PASS |
| Releasing the button again leaves the LED off. | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button again leaves the LED off. | `final_level` | = 0 | 0 | ✅ PASS |

## What to fix

### ❌ The first press prints ON on its own line on Serial1. (`text`)

- **Why:** received "OFF\\r\\n", but expected matches /^ON\\r?\\n$/
- **Feedback:** The LED level itself is correct, but the printed string is the state \*before\* the toggle rather than after. In loop(), line 36 prints \`ledOn ? "ON" : "OFF"\` and only then line 37 flips \`ledOn = !ledOn;\`, so the message always lags one step behind the actual new LED state. On the first press ledOn starts false, so it prints "OFF" even though the LED is being turned on. Swap the order (toggle ledOn first, then print the new value, or print based on the new LED\_PIN state) so the printed word matches the state you just set.
- **Where to look:** submission\_01.ino:36

### ❌ The second press prints OFF on its own line on Serial1. (`text`)

- **Why:** received "ON\\r\\n", but expected matches /^OFF\\r?\\n$/
- **Feedback:** Same cause as *The first press prints ON on its own line on Serial1.* (`text`). Same off-by-one print-before-toggle bug as the first press: the message printed is still the pre-toggle value of ledOn, so it reads "ON" instead of "OFF".
- **Where to look:** submission\_01.ino:36

## Not graded automatically

- **Implement debouncing in software, without blocking delay() calls.**: The pins can't show how the debouncing is done. Only its effect (one toggle per press, fast response) is tested.
- **Comment your code.**: Code style can't be observed electrically.

## Assumptions the grader made

- The handout gives no number for 'quickly', so the LED must change within 100 ms of the first press edge, which is about where people start to notice a delay.
- A bouncy press is 5 edges 200 us apart, ending LOW (pressed).
- Releasing the button is the board letting go of D2, so the student's INPUT\_PULLUP pulls it high.
- Serial lines may end with \\n or \\r\\n.
- Releasing the button must not toggle the LED (only presses do).
