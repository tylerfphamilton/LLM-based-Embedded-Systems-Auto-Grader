# Autograder report: uart_id_opus_p

**Submission:** `hex_lowercase`  
**Result: 9 of 11 checks passed** · 2 failed · 0 borderline · 0 could not be measured

> Serial1 (9600 8N1) command responder: ID?, SUM?, HEX? answered with per-student values, ERR for unknown commands, empty lines ignored, no extra output.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The sketch prints nothing on Serial1 after start-up (no start-up message or debug output). | `byte_count` | = 0 | 0 | ✅ PASS |
| Sending 'ID?' ending in \\n gets your 9-digit ID (with leading zeros) back as one line. | `text` | matches /^000745619\\r?\\n$/ | "000745619\\r\\n" | ✅ PASS |
| Sending 'ID?' ending in \\n gets your 9-digit ID (with leading zeros) back as one line. | `framing_errors` | = 0 | 0 | ✅ PASS |
| Sending 'SUM?' ending in \\r\\n gets the sum of your ID's digits back as one line. | `text` | matches /^32\\r?\\n$/ | "32\\r\\n" | ✅ PASS |
| Sending 'HEX?' gets your ID as upper-case hex with no leading zeros back as one line. | `text` | matches /^B6093\\r?\\n$/ | "b6093\\r\\n" | ❌ FAIL |
| Sending 'HEX?' ending in \\r\\n also gets the hex ID back (the \\r is not part of the command). | `text` | matches /^B6093\\r?\\n$/ | "b6093\\r\\n" | ❌ FAIL |
| An unknown command gets 'ERR' back as one line. | `text` | matches /^ERR\\r?\\n$/ | "ERR\\r\\n" | ✅ PASS |
| Empty lines are ignored and get no reply. | `byte_count` | = 0 | 0 | ✅ PASS |
| Sending 'SUM?' ending in \\n also gets the digit sum back. | `text` | matches /^32\\r?\\n$/ | "32\\r\\n" | ✅ PASS |
| The sketch keeps answering: 'ID?' sent again (ending in \\r\\n) still gets your ID back. | `text` | matches /^000745619\\r?\\n$/ | "000745619\\r\\n" | ✅ PASS |
| The sketch keeps answering: 'ID?' sent again (ending in \\r\\n) still gets your ID back. | `framing_errors` | = 0 | 0 | ✅ PASS |

## What to fix

### ❌ Sending 'HEX?' gets your ID as upper-case hex with no leading zeros back as one line. (`text`)

- **Why:** received "b6093\\r\\n", but expected matches /^B6093\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

### ❌ Sending 'HEX?' ending in \\r\\n also gets the hex ID back (the \\r is not part of the command). (`text`)

- **Why:** received "b6093\\r\\n", but expected matches /^B6093\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

## Not graded automatically

- **Comment your code.**: Code comments cannot be observed electrically.

## Assumptions the grader made

- The handout does not define 'promptly'; each reply must arrive within a 500 ms window after the command is sent.
- A reply is accepted with either a \\r\\n or a \\n line ending, and nothing else may be sent in the window.
- Silence at start-up is checked for 1000 ms after the 1000 ms boot wait; output sent earlier than that is not seen.
- Answering for as long as the board is powered is checked by sending ID? again at the end of the test; longer operation is not tested.
