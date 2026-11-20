# Autograder report: button_toggle_opus_b

**Submission:** `submission_08`  
**Result: 11 of 16 checks passed** · 5 failed · 0 borderline · 0 could not be measured

> Debounced button toggle: button on D2 (active low, INPUT_PULLUP) toggles the LED on D13 once per bouncy press and prints ON/OFF on Serial1 at 9600 baud.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The LED is off after reset. | `final_level` | = 0 | 0 | ✅ PASS |
| The LED is off after reset. | `edge_count` | = 0 | 0 | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `delay_ms` | any value (not null) | 5.721 ms | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | 5.721 ms | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `to_edge_count` | = 1 | 1 | ✅ PASS |
| The first press prints ON on its own line on Serial1. | `text` | matches /^ON\\r?\\n$/ | "ON\\r\\n" | ✅ PASS |
| The first press prints ON on its own line on Serial1. | `framing_errors` | = 0 | 0 | ✅ PASS |
| Releasing the button does not change the LED (it stays on). | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button does not change the LED (it stays on). | `final_level` | = 1 | 1 | ✅ PASS |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | any value (not null) | no value (null) | ❌ FAIL |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | no value (null) | ❌ FAIL |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `to_edge_count` | = 1 | 0 | ❌ FAIL |
| The second press prints OFF on its own line on Serial1. | `text` | matches /^OFF\\r?\\n$/ | "" | ❌ FAIL |
| The second press prints OFF on its own line on Serial1. | `framing_errors` | = 0 | 0 | ✅ PASS |
| Releasing the button again leaves the LED off. | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button again leaves the LED off. | `final_level` | = 0 | 1 | ❌ FAIL |

## What to fix

### ❌ The second bouncy press turns the LED off exactly once, within 100 ms. (`delay_ms`)

- **Why:** measured no value (null), but expected any value (not null)
- **Possible causes:** No edge on D13 and no OFF text were seen for the second press at all (to\_edge\_count=0, delay\_ms=null, text=""), meaning the toggle branch at lines 37-41 never ran for the second press, not just late. Top candidates: (1) the shared debounce state (lastSample/btnState/sampleChangedAt, lines 13-15, updated at 30-36) may not actually flip btnState back to HIGH during the release before the second press's bounces start, so on the second press 'sample != btnState' is already false and the if-block at 35 never triggers — check with a debug print of btnState right after line 36 during release; (2) verify digitalRead(BTN\_PIN) at line 28 is actually seeing the new low level (e.g. nothing else is overwriting BTN\_PIN's mode/pullup after setup); (3) less likely, something in Serial1.println (line 40) or earlier blocking the loop long enough to miss the debounce window, which could be ruled out by toggling a spare pin each loop iteration.
- **Where to look:** submission\_08.ino:35

### ❌ The second bouncy press turns the LED off exactly once, within 100 ms. (`delay_ms`)

- **Why:** nothing was measured for 'delay\_ms' (null, e.g. no signal or no response); expected ≤ 100 ms
- **Possible causes:** Same cause as *The second bouncy press turns the LED off exactly once, within 100 ms.* (`delay_ms`). Same missing-toggle-on-second-press issue as the other press2\_led check.
- **Where to look:** submission\_08.ino:35

### ❌ The second bouncy press turns the LED off exactly once, within 100 ms. (`to_edge_count`)

- **Why:** measured 0, but expected = 1
- **Possible causes:** Same cause as *The second bouncy press turns the LED off exactly once, within 100 ms.* (`delay_ms`). Zero edges on D13 confirms the toggle branch did not execute on the second press, same root cause as the delay\_ms failure above.
- **Where to look:** submission\_08.ino:35

### ❌ The second press prints OFF on its own line on Serial1. (`text`)

- **Why:** received "", but expected matches /^OFF\\r?\\n$/
- **Possible causes:** Same cause as *The second bouncy press turns the LED off exactly once, within 100 ms.* (`delay_ms`). Since the toggle branch (lines 37-41, which also contains the Serial1.println) never ran on the second press, no "OFF" line was ever sent — same root cause as the LED not toggling.
- **Where to look:** submission\_08.ino:40

### ❌ Releasing the button again leaves the LED off. (`final_level`)

- **Why:** measured 1, but expected = 0
- **Possible causes:** Same cause as *The second bouncy press turns the LED off exactly once, within 100 ms.* (`delay_ms`). The LED is still reported as on (1) because it was never turned off in the first place — the second press never toggled it, so this is the same underlying bug as the press2 failures above, not a separate release-handling issue.
- **Where to look:** submission\_08.ino:35

## Not graded automatically

- **Implement debouncing in software, without blocking delay() calls.**: The pins can't show how the debouncing is done. Only its effect (one toggle per press, fast response) is tested.
- **Comment your code.**: Code style can't be observed electrically.

## Assumptions the grader made

- The handout gives no number for 'quickly', so the LED must change within 100 ms of the first press edge, which is about where people start to notice a delay.
- A bouncy press is 5 edges 200 us apart, ending LOW (pressed).
- Releasing the button is the board letting go of D2, so the student's INPUT\_PULLUP pulls it high.
- Serial lines may end with \\n or \\r\\n.
- Releasing the button must not toggle the LED (only presses do).
