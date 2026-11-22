# Autograder report: button_toggle

**Submission:** `submission_04`  
**Result: 4 of 11 checks passed** · 7 failed · 0 borderline · 0 could not be measured

> A bouncy active-low button on D2 toggles the LED on D13 within 20 ms and prints ON/OFF on Serial1 at 9600 baud; bounce must be ignored.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| First press turns the LED on within 20 ms, exactly once despite bounce | `delay_ms` | ≤ 20 ms | no value (null) | ❌ FAIL |
| First press turns the LED on within 20 ms, exactly once despite bounce | `to_edge_count` | = 1 | 0 | ❌ FAIL |
| First press prints ON on Serial1 at 9600 baud | `text` | matches /^\\s\*ON\\s\*$/ | "" | ❌ FAIL |
| First press prints ON on Serial1 at 9600 baud | `framing_errors` | = 0 | 0 | ✅ PASS |
| Releasing the button (with bounce) does not change the LED | `edge_count` | = 0 | 0 | ✅ PASS |
| Releasing the button (with bounce) does not change the LED | `final_level` | = 1 | 0 | ❌ FAIL |
| Second press turns the LED off within 20 ms, exactly once despite bounce | `delay_ms` | ≤ 20 ms | no value (null) | ❌ FAIL |
| Second press turns the LED off within 20 ms, exactly once despite bounce | `to_edge_count` | = 1 | 0 | ❌ FAIL |
| Second press prints OFF on Serial1 at 9600 baud | `text` | matches /^\\s\*OFF\\s\*$/ | "" | ❌ FAIL |
| Second press prints OFF on Serial1 at 9600 baud | `framing_errors` | = 0 | 0 | ✅ PASS |
| D2 has a pull-up: with the button released, the pin reads high | `final_level` | = 1 | 1 | ✅ PASS |

## What to fix

### ❌ First press turns the LED on within 20 ms, exactly once despite bounce (`delay_ms`)

- **Why:** nothing was measured for 'delay\_ms' (null, e.g. no signal or no response); expected ≤ 20 ms
- **Feedback:** _Detailed feedback is not available yet._

### ❌ First press turns the LED on within 20 ms, exactly once despite bounce (`to_edge_count`)

- **Why:** measured 0, but expected = 1
- **Feedback:** _Detailed feedback is not available yet._

### ❌ First press prints ON on Serial1 at 9600 baud (`text`)

- **Why:** received "", but expected matches /^\\s\*ON\\s\*$/
- **Feedback:** _Detailed feedback is not available yet._

### ❌ Releasing the button (with bounce) does not change the LED (`final_level`)

- **Why:** measured 0, but expected = 1
- **Feedback:** _Detailed feedback is not available yet._

### ❌ Second press turns the LED off within 20 ms, exactly once despite bounce (`delay_ms`)

- **Why:** nothing was measured for 'delay\_ms' (null, e.g. no signal or no response); expected ≤ 20 ms
- **Feedback:** _Detailed feedback is not available yet._

### ❌ Second press turns the LED off within 20 ms, exactly once despite bounce (`to_edge_count`)

- **Why:** measured 0, but expected = 1
- **Feedback:** _Detailed feedback is not available yet._

### ❌ Second press prints OFF on Serial1 at 9600 baud (`text`)

- **Why:** received "", but expected matches /^\\s\*OFF\\s\*$/
- **Feedback:** _Detailed feedback is not available yet._

## Not graded automatically

- **Debounce is implemented in software (not with delay())**: Only the observable behaviour (one LED edge per press) is graded
- **Code is commented and readable**: Not observable electrically

## Assumptions the grader made

- The student enables the internal pull-up on D2 (INPUT\_PULLUP); the rig releases D2 (high-Z) when the button is not pressed, and checks once, after releasing straight from low, that D2 then reads high
- A bouncy press or release is 7 level changes 1 ms apart (about 6 ms of bounce)
- The LED starts off after reset, so the first press prints ON
- Each message is a single line; trailing CR/LF is ignored
