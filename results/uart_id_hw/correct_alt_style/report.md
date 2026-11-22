# Autograder report: uart_id

**Submission:** `correct_alt_style`  
**Result: 12 of 12 checks passed** · 0 failed · 0 borderline · 0 could not be measured

> The sketch answers ID?, SUM? and HEX? on Serial1 at 9600 baud with values derived from the student's own ID, and ERR for anything else.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| ID? (ended by \\n) replies with your ID on one line | `text` | matches /^000527164\\r?\\n$/ | "000527164\\n" | ✅ PASS |
| ID? (ended by \\n) replies with your ID on one line | `framing_errors` | = 0 | 0 | ✅ PASS |
| SUM? replies with the sum of your ID's digits | `text` | matches /^25\\r?\\n$/ | "25\\n" | ✅ PASS |
| SUM? replies with the sum of your ID's digits | `framing_errors` | = 0 | 0 | ✅ PASS |
| HEX? replies with your ID in upper-case hex, without leading zeros | `text` | matches /^80B3C\\r?\\n$/ | "80B3C\\n" | ✅ PASS |
| HEX? replies with your ID in upper-case hex, without leading zeros | `framing_errors` | = 0 | 0 | ✅ PASS |
| ID? ended by \\r\\n is accepted too | `text` | matches /^000527164\\r?\\n$/ | "000527164\\n" | ✅ PASS |
| ID? ended by \\r\\n is accepted too | `framing_errors` | = 0 | 0 | ✅ PASS |
| An unknown command replies ERR | `text` | matches /^ERR\\r?\\n$/ | "ERR\\n" | ✅ PASS |
| An unknown command replies ERR | `framing_errors` | = 0 | 0 | ✅ PASS |
| The sketch keeps answering: a final ID? still replies with your ID | `text` | matches /^000527164\\r?\\n$/ | "000527164\\n" | ✅ PASS |
| The sketch keeps answering: a final ID? still replies with your ID | `framing_errors` | = 0 | 0 | ✅ PASS |

## Not graded automatically

- **Code is commented and readable**: Not observable electrically

## Assumptions the grader made

- The plan first sends one empty line, unchecked, to flush anything the Nano's receiver picked up when the rig first drove its line; whatever the sketch does with it is ignored, and the next command is sent 200 ms later
- "Reply promptly" is taken as: the whole reply line arrives within 300 ms of the measurement starting (sending a command takes about 5 ms at 9600 baud); a reply that arrives later lands in the next check
- Each reply is exactly one line: the value, then \\n or \\r\\n, with nothing before or after it
- No boot message is checked: the rig can only start reading after the reset and boot wait, so anything printed during boot is lost
