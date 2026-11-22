# Autograder report: button_toggle_sonnet_c

**Submission:** `usb_serial`  
**Result: 20 of 23 checks passed** · 3 failed · 0 borderline · 0 could not be measured

> Checks LED off after reset, one toggle per bouncy press, quick reaction, ON/OFF lines on Serial1 at 9600 baud, no toggle on release, and the internal pull-up.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The LED is off after reset and does not blink. | `final_level` | = 0 | 0 | ✅ PASS |
| The LED is off after reset and does not blink. | `edge_count` | = 0 | 0 | ✅ PASS |
| The first bouncy press turns the LED on quickly, with exactly one LED change. | `delay_ms` | any value (not null) | 10.058 ms | ✅ PASS |
| The first bouncy press turns the LED on quickly, with exactly one LED change. | `delay_ms` | ≤ 50 ms | 10.058 ms | ✅ PASS |
| The first bouncy press turns the LED on quickly, with exactly one LED change. | `to_edge_count` | = 1 | 1 | ✅ PASS |
| The first press prints exactly one line ON on Serial1. | `text` | matches /^ON\\r?\\n$/ | "" | ❌ FAIL |
| The first press prints exactly one line ON on Serial1. | `framing_errors` | = 0 | 0 | ✅ PASS |
| Releasing the button (with bounce) does not change the LED, which stays on. | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button (with bounce) does not change the LED, which stays on. | `final_level` | = 1 | 1 | ✅ PASS |
| Releasing the button prints nothing. | `byte_count` | = 0 | 0 | ✅ PASS |
| The second bouncy press turns the LED off quickly, with exactly one LED change. | `delay_ms` | any value (not null) | 10.556 ms | ✅ PASS |
| The second bouncy press turns the LED off quickly, with exactly one LED change. | `delay_ms` | ≤ 50 ms | 10.556 ms | ✅ PASS |
| The second bouncy press turns the LED off quickly, with exactly one LED change. | `to_edge_count` | = 1 | 1 | ✅ PASS |
| The second press prints exactly one line OFF on Serial1. | `text` | matches /^OFF\\r?\\n$/ | "" | ❌ FAIL |
| The second press prints exactly one line OFF on Serial1. | `framing_errors` | = 0 | 0 | ✅ PASS |
| Releasing the button (with bounce) does not change the LED, which stays off. | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button (with bounce) does not change the LED, which stays off. | `final_level` | = 0 | 0 | ✅ PASS |
| Releasing the button prints nothing. | `byte_count` | = 0 | 0 | ✅ PASS |
| The third bouncy press turns the LED on again, with exactly one LED change. | `delay_ms` | any value (not null) | 10.463 ms | ✅ PASS |
| The third bouncy press turns the LED on again, with exactly one LED change. | `delay_ms` | ≤ 50 ms | 10.463 ms | ✅ PASS |
| The third bouncy press turns the LED on again, with exactly one LED change. | `to_edge_count` | = 1 | 1 | ✅ PASS |
| The third press prints exactly one line ON on Serial1. | `text` | matches /^ON\\r?\\n$/ | "" | ❌ FAIL |
| The button pin uses the internal pull-up, so it reads high when released. | `final_level` | = 1 | 1 | ✅ PASS |

## What to fix

### ❌ The first press prints exactly one line ON on Serial1. (`text`)

- **Why:** received "", but expected matches /^ON\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

### ❌ The second press prints exactly one line OFF on Serial1. (`text`)

- **Why:** received "", but expected matches /^OFF\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

### ❌ The third press prints exactly one line ON on Serial1. (`text`)

- **Why:** received "", but expected matches /^ON\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

## Not graded automatically

- **Implement debouncing in software, without blocking delay() calls**: Code structure is not directly observable electrically; only the debounced behaviour is graded.
- **Comment your code**: Comments cannot be observed electrically.

## Assumptions the grader made

- The handout gives no number for 'quickly', so I use at most 50 ms from the first press edge to the LED change (this includes about 7 ms of contact bounce).
- Line ending is not specified, so I accept either LF or CRLF after ON/OFF.
- Each bounce is 7 edges at 1 ms intervals (7 ms), as the rig guidance recommends.
- Quiet windows of 50 ms (after reset and for the pull-up check) and 500 ms (after a press) are my own choice.
