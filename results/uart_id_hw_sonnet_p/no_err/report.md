# Autograder report: uart_id_sonnet_p

**Submission:** `no_err`  
**Result: 12 of 14 checks passed** · 2 failed · 0 borderline · 0 could not be measured

> Checks the Serial1 ID responder at 9600 baud: silent after boot, correct replies for ID?/SUM?/HEX?, ERR for unknown commands, both line endings, empty lines ignored, and still answering later.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The sketch prints nothing on Serial1 until it receives a command. | `byte_count` | = 0 | 0 | ✅ PASS |
| ID? (ending in \\n) is answered with your 9-digit ID, leading zeros kept. | `text` | matches /^000276548\\r?\\n$/ | "000276548\\r\\n" | ✅ PASS |
| ID? (ending in \\n) is answered with your 9-digit ID, leading zeros kept. | `framing_errors` | = 0 | 0 | ✅ PASS |
| ID? ending in \\r\\n is accepted and answered with your ID. | `text` | matches /^000276548\\r?\\n$/ | "000276548\\r\\n" | ✅ PASS |
| SUM? is answered with the sum of your ID digits. | `text` | matches /^32\\r?\\n$/ | "32\\r\\n" | ✅ PASS |
| SUM? ending in \\r\\n is accepted. | `text` | matches /^32\\r?\\n$/ | "32\\r\\n" | ✅ PASS |
| HEX? is answered with your ID in upper-case hex without leading zeros. | `text` | matches /^43844\\r?\\n$/ | "43844\\r\\n" | ✅ PASS |
| HEX? ending in \\r\\n is accepted. | `text` | matches /^43844\\r?\\n$/ | "43844\\r\\n" | ✅ PASS |
| An unknown command is answered with ERR. | `text` | matches /^ERR\\r?\\n$/ | "" | ❌ FAIL |
| An unknown command ending in \\r\\n gives ERR (the \\r is not part of the command). | `text` | matches /^ERR\\r?\\n$/ | "" | ❌ FAIL |
| Empty lines are ignored: only the ID reply comes back. | `text` | matches /^000276548\\r?\\n$/ | "000276548\\r\\n" | ✅ PASS |
| Several commands sent back to back each get their own reply, in order. | `text` | matches /^000276548\\r?\\n32\\r?\\n43844\\r?\\n$/ | "000276548\\r\\n32\\r\\n43844\\r\\n" | ✅ PASS |
| The sketch keeps answering after it has been running for a while. | `text` | matches /^000276548\\r?\\n$/ | "000276548\\r\\n" | ✅ PASS |
| Nothing extra is printed after the replies. | `byte_count` | = 0 | 0 | ✅ PASS |

## What to fix

### ❌ An unknown command is answered with ERR. (`text`)

- **Why:** received "", but expected matches /^ERR\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

### ❌ An unknown command ending in \\r\\n gives ERR (the \\r is not part of the command). (`text`)

- **Why:** received "", but expected matches /^ERR\\r?\\n$/
- **Feedback:** _Detailed feedback is not available yet._

## Not graded automatically

- **Comment your code.**: Code comments cannot be observed electrically.

## Assumptions the grader made

- The handout gives no reply deadline, so each reply must arrive within a 300 ms window (800 ms for three back-to-back commands).
- The silence check runs after the 1000 ms boot wait, so it only sees output printed after the board has finished starting.
- Replies may end in \\n or \\r\\n, so the expected text allows an optional \\r before the final \\n.
- Unknown-command tests use HELLO and XYZ? as examples of anything else.
