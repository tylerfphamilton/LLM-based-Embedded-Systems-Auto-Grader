# Autograder report: uart_id_sonnet_p

**Submission:** `copied_id`  
**Result: 5 of 14 checks passed** · 9 failed · 0 borderline · 0 could not be measured

> Checks the Serial1 ID responder at 9600 baud: silent after boot, correct replies for ID?/SUM?/HEX?, ERR for unknown commands, both line endings, empty lines ignored, and still answering later.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The sketch prints nothing on Serial1 until it receives a command. | `byte_count` | = 0 | 0 | ✅ PASS |
| ID? (ending in \\n) is answered with your 9-digit ID, leading zeros kept. | `text` | matches /^000638205\\r?\\n$/ | "000412387\\r\\n" | ❌ FAIL |
| ID? (ending in \\n) is answered with your 9-digit ID, leading zeros kept. | `framing_errors` | = 0 | 0 | ✅ PASS |
| ID? ending in \\r\\n is accepted and answered with your ID. | `text` | matches /^000638205\\r?\\n$/ | "000412387\\r\\n" | ❌ FAIL |
| SUM? is answered with the sum of your ID digits. | `text` | matches /^24\\r?\\n$/ | "25\\r\\n" | ❌ FAIL |
| SUM? ending in \\r\\n is accepted. | `text` | matches /^24\\r?\\n$/ | "25\\r\\n" | ❌ FAIL |
| HEX? is answered with your ID in upper-case hex without leading zeros. | `text` | matches /^9BCFD\\r?\\n$/ | "64AE3\\r\\n" | ❌ FAIL |
| HEX? ending in \\r\\n is accepted. | `text` | matches /^9BCFD\\r?\\n$/ | "64AE3\\r\\n" | ❌ FAIL |
| An unknown command is answered with ERR. | `text` | matches /^ERR\\r?\\n$/ | "ERR\\r\\n" | ✅ PASS |
| An unknown command ending in \\r\\n gives ERR (the \\r is not part of the command). | `text` | matches /^ERR\\r?\\n$/ | "ERR\\r\\n" | ✅ PASS |
| Empty lines are ignored: only the ID reply comes back. | `text` | matches /^000638205\\r?\\n$/ | "000412387\\r\\n" | ❌ FAIL |
| Several commands sent back to back each get their own reply, in order. | `text` | matches /^000638205\\r?\\n24\\r?\\n9BCFD\\r?\\n$/ | "000412387\\r\\n25\\r\\n64AE3\\r\\n" | ❌ FAIL |
| The sketch keeps answering after it has been running for a while. | `text` | matches /^000638205\\r?\\n$/ | "000412387\\r\\n" | ❌ FAIL |
| Nothing extra is printed after the replies. | `byte_count` | = 0 | 0 | ✅ PASS |

## What to fix

### ❌ ID? (ending in \\n) is answered with your 9-digit ID, leading zeros kept. (`text`)

- **Why:** received "000412387\\r\\n", but expected matches /^000638205\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

### ❌ ID? ending in \\r\\n is accepted and answered with your ID. (`text`)

- **Why:** received "000412387\\r\\n", but expected matches /^000638205\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

### ❌ SUM? is answered with the sum of your ID digits. (`text`)

- **Why:** received "25\\r\\n", but expected matches /^24\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

### ❌ SUM? ending in \\r\\n is accepted. (`text`)

- **Why:** received "25\\r\\n", but expected matches /^24\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

### ❌ HEX? is answered with your ID in upper-case hex without leading zeros. (`text`)

- **Why:** received "64AE3\\r\\n", but expected matches /^9BCFD\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

### ❌ HEX? ending in \\r\\n is accepted. (`text`)

- **Why:** received "64AE3\\r\\n", but expected matches /^9BCFD\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

### ❌ Empty lines are ignored: only the ID reply comes back. (`text`)

- **Why:** received "000412387\\r\\n", but expected matches /^000638205\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

### ❌ Several commands sent back to back each get their own reply, in order. (`text`)

- **Why:** received "000412387\\r\\n25\\r\\n64AE3\\r\\n", but expected matches /^000638205\\r?\\n24\\r?\\n9BCFD\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

### ❌ The sketch keeps answering after it has been running for a while. (`text`)

- **Why:** received "000412387\\r\\n", but expected matches /^000638205\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

## Not graded automatically

- **Comment your code.**: Code comments cannot be observed electrically.

## Assumptions the grader made

- The handout gives no reply deadline, so each reply must arrive within a 300 ms window (800 ms for three back-to-back commands).
- The silence check runs after the 1000 ms boot wait, so it only sees output printed after the board has finished starting.
- Replies may end in \\n or \\r\\n, so the expected text allows an optional \\r before the final \\n.
- Unknown-command tests use HELLO and XYZ? as examples of anything else.
