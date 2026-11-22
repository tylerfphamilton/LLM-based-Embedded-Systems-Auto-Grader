# Autograder report: button_toggle_opus_c

**Submission:** `usb_serial`  
**Result: 18 of 20 checks passed** · 2 failed · 0 borderline · 0 could not be measured

> Debounced push-button toggle of the D13 LED with ON/OFF reports on Serial1 at 9600 baud. Checks the LED is off at start, that bouncy presses toggle exactly once and quickly, that bouncy releases do not toggle, the serial messages, and the internal pull-up on D2.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The LED is off after reset and stays off while the button is not pressed. | `final_level` | = 0 | 0 | ✅ PASS |
| The LED is off after reset and stays off while the button is not pressed. | `edge_count` | = 0 | 0 | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `delay_ms` | any value (not null) | 10.96 ms | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | 10.96 ms | ✅ PASS |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `to_edge_count` | = 1 | 1 | ✅ PASS |
| After the first press the sketch prints ON on its own line on Serial1 at 9600 baud. | `text` | matches /^ON\\r?\\n$/ | "" | ❌ FAIL |
| After the first press the sketch prints ON on its own line on Serial1 at 9600 baud. | `framing_errors` | = 0 | 0 | ✅ PASS |
| The LED stays on after the first press. | `final_level` | = 1 | 1 | ✅ PASS |
| The LED stays on after the first press. | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button, even with bounce, does not change the LED. | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button, even with bounce, does not change the LED. | `final_level` | = 1 | 1 | ✅ PASS |
| Releasing the button prints nothing on Serial1. | `byte_count` | = 0 | 0 | ✅ PASS |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | any value (not null) | 10.643 ms | ✅ PASS |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | 10.643 ms | ✅ PASS |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `to_edge_count` | = 1 | 1 | ✅ PASS |
| After the second press the sketch prints OFF on its own line on Serial1. | `text` | matches /^OFF\\r?\\n$/ | "" | ❌ FAIL |
| After the second press the sketch prints OFF on its own line on Serial1. | `framing_errors` | = 0 | 0 | ✅ PASS |
| The LED stays off after the second press. | `final_level` | = 0 | 0 | ✅ PASS |
| The LED stays off after the second press. | `edge_count` | = 0 | 0 | ✅ PASS |
| The button pin uses the internal pull-up, so it reads HIGH when the button is not pressed. | `final_level` | = 1 | 1 | ✅ PASS |

## What to fix

### ❌ After the first press the sketch prints ON on its own line on Serial1 at 9600 baud. (`text`)

- **Why:** received "", but expected matches /^ON\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

### ❌ After the second press the sketch prints OFF on its own line on Serial1. (`text`)

- **Why:** received "", but expected matches /^OFF\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

## Not graded automatically

- **Implement debouncing in software, without blocking delay() calls.**: How the debouncing is coded can't be seen from the pins. Only how it behaves (one toggle per bouncy press) is graded.
- **Comment your code.**: Code style and comments can't be measured electrically.

## Assumptions the grader made

- The handout gives no number for 'quickly', so the LED must change within 100 ms of the first press edge, which is about when people start to notice a delay.
- Each press and the first release are bounced 7 times at 1 ms (7 ms of bounce) to check debouncing.
- Serial lines may end in either \\n or \\r\\n (println style), and nothing else may be printed during a toggle.
- The LED is active-high (HIGH = on), as with the Nano 33 BLE on-board LED on D13.
- The 'exactly once' check counts every LED edge for 500 ms after the press, so a sketch that toggles again late is also caught.
