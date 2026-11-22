# Autograder report: uart_id

**Submission:** `ascii_sum`  
**Result: 11 of 12 checks passed** · 1 failed · 0 borderline · 0 could not be measured

> The sketch answers ID?, SUM? and HEX? on Serial1 at 9600 baud with values derived from the student's own ID, and ERR for anything else.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| ID? (ended by \\n) replies with your ID on one line | `text` | matches /^000194726\\r?\\n$/ | "000194726\\r\\n" | ✅ PASS |
| ID? (ended by \\n) replies with your ID on one line | `framing_errors` | = 0 | 0 | ✅ PASS |
| SUM? replies with the sum of your ID's digits | `text` | matches /^29\\r?\\n$/ | "461\\r\\n" | ❌ FAIL |
| SUM? replies with the sum of your ID's digits | `framing_errors` | = 0 | 0 | ✅ PASS |
| HEX? replies with your ID in upper-case hex, without leading zeros | `text` | matches /^2F8A6\\r?\\n$/ | "2F8A6\\r\\n" | ✅ PASS |
| HEX? replies with your ID in upper-case hex, without leading zeros | `framing_errors` | = 0 | 0 | ✅ PASS |
| ID? ended by \\r\\n is accepted too | `text` | matches /^000194726\\r?\\n$/ | "000194726\\r\\n" | ✅ PASS |
| ID? ended by \\r\\n is accepted too | `framing_errors` | = 0 | 0 | ✅ PASS |
| An unknown command replies ERR | `text` | matches /^ERR\\r?\\n$/ | "ERR\\r\\n" | ✅ PASS |
| An unknown command replies ERR | `framing_errors` | = 0 | 0 | ✅ PASS |
| The sketch keeps answering: a final ID? still replies with your ID | `text` | matches /^000194726\\r?\\n$/ | "000194726\\r\\n" | ✅ PASS |
| The sketch keeps answering: a final ID? still replies with your ID | `framing_errors` | = 0 | 0 | ✅ PASS |

## What to fix

### ❌ SUM? replies with the sum of your ID's digits (`text`)

- **Why:** received "461\\r\\n", but expected matches /^29\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

## Not graded automatically

- **Code is commented and readable**: Not observable electrically

## Assumptions the grader made

- The plan first sends one empty line, unchecked, to flush anything the Nano's receiver picked up when the rig first drove its line; whatever the sketch does with it is ignored, and the next command is sent 200 ms later
- "Reply promptly" is taken as: the whole reply line arrives within 300 ms of the measurement starting (sending a command takes about 5 ms at 9600 baud); a reply that arrives later lands in the next check
- Each reply is exactly one line: the value, then \\n or \\r\\n, with nothing before or after it
- No boot message is checked: the rig can only start reading after the reset and boot wait, so anything printed during boot is lost
