# Autograder report: button_toggle_opus_b

**Submission:** `toggle_on_release`  
**Result: 6 of 16 checks passed** · 10 failed · 0 borderline · 0 could not be measured

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
| Releasing the button does not change the LED (it stays on). | `edge_count` | = 0 | 1 | ❌ FAIL |
| Releasing the button does not change the LED (it stays on). | `final_level` | = 1 | 1 | ✅ PASS |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | any value (not null) | no value (null) | ❌ FAIL |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | no value (null) | ❌ FAIL |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `to_edge_count` | = 1 | 0 | ❌ FAIL |
| The second press prints OFF on its own line on Serial1. | `text` | matches /^OFF\\r?\\n$/ | "" | ❌ FAIL |
| The second press prints OFF on its own line on Serial1. | `framing_errors` | = 0 | 0 | ✅ PASS |
| Releasing the button again leaves the LED off. | `edge_count` | = 0 | 1 | ❌ FAIL |
| Releasing the button again leaves the LED off. | `final_level` | = 0 | 0 | ✅ PASS |

## What to fix

### ❌ The first bouncy press turns the LED on exactly once, within 100 ms. (`delay_ms`)

- **Why:** measured no value (null), but expected any value (not null)
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: the toggle fires on release, not during the press window, so no LED transition is observed here.
- **Where to look:** toggle\_on\_release.ino:27

### ❌ The first bouncy press turns the LED on exactly once, within 100 ms. (`delay_ms`)

- **Why:** nothing was measured for 'delay\_ms' (null, e.g. no signal or no response); expected ≤ 100 ms
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: the toggle fires on release, not during the press window, so no LED transition is observed within the 100 ms limit.
- **Where to look:** toggle\_on\_release.ino:27

### ❌ The first bouncy press turns the LED on exactly once, within 100 ms. (`to_edge_count`)

- **Why:** measured 0, but expected = 1
- **Feedback:** In loop(), the toggle only executes when the debounced level becomes HIGH (line 27: \`if (stable == HIGH)\`). Since BTN\_PIN uses INPUT\_PULLUP and the button is active-low, HIGH is the \*released\* state, not the pressed one - so the LED and the print happen one step late, on release instead of on press. That is why no LED edge or ON print is seen while the button is held down (press1), but the toggle instead shows up when the button comes back up.
- **Where to look:** toggle\_on\_release.ino:27

### ❌ The first press prints ON on its own line on Serial1. (`text`)

- **Why:** received "", but expected matches /^ON\\r?\\n$/
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: the \`Serial1.println(on ? "ON" : "OFF")\` call is inside the same \`if (stable == HIGH)\` block, so it only runs on release, producing no text during the press window.
- **Where to look:** toggle\_on\_release.ino:30

### ❌ Releasing the button does not change the LED (it stays on). (`edge_count`)

- **Why:** measured 1, but expected = 0
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: because the toggle is keyed to HIGH (release) instead of LOW (press), releasing the button after the first press causes the LED to flip - which should not happen per the requirement.
- **Where to look:** toggle\_on\_release.ino:27

### ❌ The second bouncy press turns the LED off exactly once, within 100 ms. (`delay_ms`)

- **Why:** measured no value (null), but expected any value (not null)
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: toggling on release instead of press shifts all LED transitions by one button phase, so the second press window shows no edge.
- **Where to look:** toggle\_on\_release.ino:27

### ❌ The second bouncy press turns the LED off exactly once, within 100 ms. (`delay_ms`)

- **Why:** nothing was measured for 'delay\_ms' (null, e.g. no signal or no response); expected ≤ 100 ms
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: toggling on release instead of press shifts all LED transitions by one button phase, so nothing is seen within the 100 ms window for the second press.
- **Where to look:** toggle\_on\_release.ino:27

### ❌ The second bouncy press turns the LED off exactly once, within 100 ms. (`to_edge_count`)

- **Why:** measured 0, but expected = 1
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: toggling on release instead of press shifts all LED transitions by one button phase, so no edge occurs during the second press.
- **Where to look:** toggle\_on\_release.ino:27

### ❌ The second press prints OFF on its own line on Serial1. (`text`)

- **Why:** received "", but expected matches /^OFF\\r?\\n$/
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: the OFF print is tied to the same HIGH-triggered block, so it is emitted on release rather than during the second press window.
- **Where to look:** toggle\_on\_release.ino:30

### ❌ Releasing the button again leaves the LED off. (`edge_count`)

- **Why:** measured 1, but expected = 0
- **Feedback:** Same cause as *The first bouncy press turns the LED on exactly once, within 100 ms.* (`to_edge_count`). Same root cause: releasing the button after the second press triggers the HIGH-based toggle condition, changing the LED when it should stay off.
- **Where to look:** toggle\_on\_release.ino:27

## Not graded automatically

- **Implement debouncing in software, without blocking delay() calls.**: The pins can't show how the debouncing is done. Only its effect (one toggle per press, fast response) is tested.
- **Comment your code.**: Code style can't be observed electrically.

## Assumptions the grader made

- The handout gives no number for 'quickly', so the LED must change within 100 ms of the first press edge, which is about where people start to notice a delay.
- A bouncy press is 5 edges 200 us apart, ending LOW (pressed).
- Releasing the button is the board letting go of D2, so the student's INPUT\_PULLUP pulls it high.
- Serial lines may end with \\n or \\r\\n.
- Releasing the button must not toggle the LED (only presses do).
