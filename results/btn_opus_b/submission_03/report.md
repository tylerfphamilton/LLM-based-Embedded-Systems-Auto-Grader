# Autograder report: button_toggle_opus_b

**Submission:** `submission_03`  
**Result: 13 of 16 checks passed** · 3 failed · 0 borderline · 0 could not be measured

> Debounced button toggle: button on D2 (active low, INPUT_PULLUP) toggles the LED on D13 once per bouncy press and prints ON/OFF on Serial1 at 9600 baud.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The LED is off after reset. | `final_level` | = 0 | 1 | ❌ FAIL |
| The LED is off after reset. | `edge_count` | = 0 | 0 | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `delay_ms` | any value (not null) | 5.21 ms | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | 5.21 ms | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `to_edge_count` | = 1 | 1 | ✅ PASS |
| The first press prints ON on its own line on Serial1. | `text` | matches /^ON\\r?\\n$/ | "ON\\r\\n" | ✅ PASS |
| The first press prints ON on its own line on Serial1. | `framing_errors` | = 0 | 0 | ✅ PASS |
| Releasing the button does not change the LED (it stays on). | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button does not change the LED (it stays on). | `final_level` | = 1 | 0 | ❌ FAIL |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | any value (not null) | 5.144 ms | ✅ PASS |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | 5.144 ms | ✅ PASS |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `to_edge_count` | = 1 | 1 | ✅ PASS |
| The second press prints OFF on its own line on Serial1. | `text` | matches /^OFF\\r?\\n$/ | "OFF\\r\\n" | ✅ PASS |
| The second press prints OFF on its own line on Serial1. | `framing_errors` | = 0 | 0 | ✅ PASS |
| Releasing the button again leaves the LED off. | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button again leaves the LED off. | `final_level` | = 0 | 1 | ❌ FAIL |

## What to fix

### ❌ The LED is off after reset. (`final_level`)

- **Why:** measured 1, but expected = 0
- **Feedback:** The measured pin level is the exact inverse of what's expected at every stage (1 instead of 0, 0 instead of 1, 1 instead of 0), which points to a polarity bug rather than a logic bug: the LED\_ON/LED\_OFF macros on lines 11-12 assume D13 is active-low, but the Nano 33 BLE's built-in LED on pin 13 is actually driven active-high (unlike the separate RGB LEDs, which are active-low). Check by wiring/datasheet or by simply swapping the LED\_ON/LED\_OFF definitions and re-testing.
- **Where to look:** submission\_03.ino:11

### ❌ Releasing the button does not change the LED (it stays on). (`final_level`)

- **Why:** measured 0, but expected = 1
- **Feedback:** Same cause as *The LED is off after reset.* (`final_level`). Same polarity inversion as the reset-state check: LED\_ON/LED\_OFF are swapped for this active-high pin.
- **Where to look:** submission\_03.ino:11

### ❌ Releasing the button again leaves the LED off. (`final_level`)

- **Why:** measured 1, but expected = 0
- **Feedback:** Same cause as *The LED is off after reset.* (`final_level`). Same polarity inversion as the reset-state check: LED\_ON/LED\_OFF are swapped for this active-high pin.
- **Where to look:** submission\_03.ino:11

## Not graded automatically

- **Implement debouncing in software, without blocking delay() calls.**: The pins can't show how the debouncing is done. Only its effect (one toggle per press, fast response) is tested.
- **Comment your code.**: Code style can't be observed electrically.

## Assumptions the grader made

- The handout gives no number for 'quickly', so the LED must change within 100 ms of the first press edge, which is about where people start to notice a delay.
- A bouncy press is 5 edges 200 us apart, ending LOW (pressed).
- Releasing the button is the board letting go of D2, so the student's INPUT\_PULLUP pulls it high.
- Serial lines may end with \\n or \\r\\n.
- Releasing the button must not toggle the LED (only presses do).
