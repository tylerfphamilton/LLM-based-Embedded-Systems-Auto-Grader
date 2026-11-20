# Autograder report: button_toggle_opus_b

**Submission:** `submission_04`  
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
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same missing-braces bug prevents the debounce logic from ever firing, so no LED edge occurs.
- **Where to look:** submission\_04.ino:24

### ❌ The first bouncy press turns the LED on exactly once, within 100 ms. (`delay_ms`)

- **Why:** nothing was measured for 'delay\_ms' (null, e.g. no signal or no response); expected ≤ 100 ms
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same missing-braces bug prevents the debounce logic from ever firing, so no LED edge occurs within the time window.
- **Where to look:** submission\_04.ino:24

### ❌ The first bouncy press turns the LED on exactly once, within 100 ms. (`to_edge_count`)

- **Why:** measured 0, but expected = 1
- **Feedback:** Lines 24-26 use an un-braced if: \`if (reading != lastReading) lastReading = reading;\` only covers the next line, so \`lastBounce = millis();\` on line 26 runs on every single loop iteration regardless of whether the reading changed. This means \`millis() - lastBounce\` is always ~0, so the debounce gate on line 29 never reaches \`debounceMs\`, and the code never updates \`buttonState\` or toggles the LED. Add braces around the whole if-block so \`lastBounce\` is only reset when the raw reading actually changes.
- **Where to look:** submission\_04.ino:24

### ❌ The first press prints ON on its own line on Serial1. (`text`)

- **Why:** received "", but expected matches /^ON\\r?\\n$/
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Since \`buttonState\` is never updated due to the debounce bug, the \`Serial1.println\` on line 36 is never reached, so nothing is transmitted.
- **Where to look:** submission\_04.ino:24

### ❌ Releasing the button does not change the LED (it stays on). (`final_level`)

- **Why:** measured 0, but expected = 1
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Because the first press never actually toggled the LED (same debounce bug), the LED is still off when the release check expects it to remain on from the earlier press.
- **Where to look:** submission\_04.ino:24

### ❌ The second bouncy press turns the LED off exactly once, within 100 ms. (`delay_ms`)

- **Why:** measured no value (null), but expected any value (not null)
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same missing-braces bug means the second press also never passes the debounce check, so the LED never toggles off.
- **Where to look:** submission\_04.ino:24

### ❌ The second bouncy press turns the LED off exactly once, within 100 ms. (`delay_ms`)

- **Why:** nothing was measured for 'delay\_ms' (null, e.g. no signal or no response); expected ≤ 100 ms
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same missing-braces bug means the second press also never passes the debounce check within the required window.
- **Where to look:** submission\_04.ino:24

### ❌ The second bouncy press turns the LED off exactly once, within 100 ms. (`to_edge_count`)

- **Why:** measured 0, but expected = 1
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same missing-braces bug prevents any state change on the second press, so no LED edge is produced.
- **Where to look:** submission\_04.ino:24

### ❌ The second press prints OFF on its own line on Serial1. (`text`)

- **Why:** received "", but expected matches /^OFF\\r?\\n$/
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Since \`buttonState\` never updates, the OFF branch of \`Serial1.println\` on line 36 is never reached either.
- **Where to look:** submission\_04.ino:24

## Not graded automatically

- **Implement debouncing in software, without blocking delay() calls.**: The pins can't show how the debouncing is done. Only its effect (one toggle per press, fast response) is tested.
- **Comment your code.**: Code style can't be observed electrically.

## Assumptions the grader made

- The handout gives no number for 'quickly', so the LED must change within 100 ms of the first press edge, which is about where people start to notice a delay.
- A bouncy press is 5 edges 200 us apart, ending LOW (pressed).
- Releasing the button is the board letting go of D2, so the student's INPUT\_PULLUP pulls it high.
- Serial lines may end with \\n or \\r\\n.
- Releasing the button must not toggle the LED (only presses do).
