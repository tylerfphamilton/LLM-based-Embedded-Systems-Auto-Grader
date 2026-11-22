# Autograder report: uart_id_opus

**Submission:** `ascii_sum`  
**Result: 8 of 9 checks passed** · 1 failed · 0 borderline · 0 could not be measured

> Checks the Serial1 (9600 8N1) command responder: no start-up output, correctly formatted replies to ID?, SUM? and HEX? with both \n and \r\n line endings, ERR for unknown commands, empty lines ignored, and that the sketch keeps answering.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The sketch prints nothing on Serial1 before it receives a command (no start-up message). | `byte_count` | = 0 | 0 | ✅ PASS |
| ID? ending in \\n gets your 9-digit ID (leading zeros kept) on one line. | `text` | matches /^\[0-9\]{9}\\r?\\n$/ | "000194726\\r\\n" | ✅ PASS |
| ID? ending in \\n gets your 9-digit ID (leading zeros kept) on one line. | `framing_errors` | = 0 | 0 | ✅ PASS |
| ID? ending in \\r\\n also gets your 9-digit ID (the \\r is not part of the command). | `text` | matches /^\[0-9\]{9}\\r?\\n$/ | "000194726\\r\\n" | ✅ PASS |
| SUM? gets the sum of your ID's digits as a decimal number on one line. | `text` | matches /^\[0-9\]{1,2}\\r?\\n$/ | "461\\r\\n" | ❌ FAIL |
| HEX? gets your ID in upper-case hex with no leading zeros on one line. | `text` | matches /^\[1-9A-F\]\[0-9A-F\]{0,7}\\r?\\n$/ | "2F8A6\\r\\n" | ✅ PASS |
| An unknown command gets the reply ERR. | `text` | matches /^ERR\\r?\\n$/ | "ERR\\r\\n" | ✅ PASS |
| Empty lines are ignored and get no reply. | `byte_count` | = 0 | 0 | ✅ PASS |
| The sketch keeps answering: a later ID? still gets your 9-digit ID. | `text` | matches /^\[0-9\]{9}\\r?\\n$/ | "000194726\\r\\n" | ✅ PASS |

## What to fix

### ❌ SUM? gets the sum of your ID's digits as a decimal number on one line. (`text`)

- **Why:** received "461\\r\\n", but expected matches /^\[0-9\]{1,2}\\r?\\n$/
- **Feedback:** In setup(), idDigitSum is computed as \`idDigitSum += studentId\[i\];\` which adds the raw ASCII character codes of the ID string (e.g. '0' = 48) instead of the numeric digit values. This produces a much larger number (461 instead of a 1-2 digit sum) consistent with adding ASCII codes rather than digits; fix by subtracting '0' from each character, i.e. \`idDigitSum += studentId\[i\] - '0';\` at ascii\_sum.ino:26.
- **Where to look:** ascii\_sum.ino:26

## Not graded automatically

- **Use your own university ID.**: The grader does not know each student's ID, so it can only check the reply format, not the actual values or whether the three replies agree with each other.
- **Comment your code.**: Code comments cannot be seen on the pins.

## Assumptions the grader made

- No per-student ID values are provided, so replies are checked only for the format the handout gives (9 digits, 1-2 decimal digits, upper-case hex without leading zeros), not for the exact values.
- The handout says 'promptly' without a time limit, so each reply must arrive completely within a 500 ms window after the command is sent.
- A reply may end with either \\r\\n or \\n, as the handout allows.
- The digit sum of a 9-digit ID is at most 81, so the SUM? reply is expected to have 1 or 2 digits.
- A 9-digit ID is at most 999999999 = 0x3B9AC9FF, so the HEX? reply is expected to have 1 to 8 hex digits with no leading zero.
- Start-up silence is checked by listening for 2000 ms after the boot wait before any command is sent.
