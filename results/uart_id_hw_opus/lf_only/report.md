# Autograder report: uart_id_opus

**Submission:** `lf_only`  
**Result: 6 of 9 checks passed** · 3 failed · 0 borderline · 0 could not be measured

> Checks the Serial1 (9600 8N1) command responder: no start-up output, correctly formatted replies to ID?, SUM? and HEX? with both \n and \r\n line endings, ERR for unknown commands, empty lines ignored, and that the sketch keeps answering.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The sketch prints nothing on Serial1 before it receives a command (no start-up message). | `byte_count` | = 0 | 0 | ✅ PASS |
| ID? ending in \\n gets your 9-digit ID (leading zeros kept) on one line. | `text` | matches /^\[0-9\]{9}\\r?\\n$/ | "000851093\\r\\n" | ✅ PASS |
| ID? ending in \\n gets your 9-digit ID (leading zeros kept) on one line. | `framing_errors` | = 0 | 0 | ✅ PASS |
| ID? ending in \\r\\n also gets your 9-digit ID (the \\r is not part of the command). | `text` | matches /^\[0-9\]{9}\\r?\\n$/ | "ERR\\r\\n" | ❌ FAIL |
| SUM? gets the sum of your ID's digits as a decimal number on one line. | `text` | matches /^\[0-9\]{1,2}\\r?\\n$/ | "26\\r\\n" | ✅ PASS |
| HEX? gets your ID in upper-case hex with no leading zeros on one line. | `text` | matches /^\[1-9A-F\]\[0-9A-F\]{0,7}\\r?\\n$/ | "ERR\\r\\n" | ❌ FAIL |
| An unknown command gets the reply ERR. | `text` | matches /^ERR\\r?\\n$/ | "ERR\\r\\n" | ✅ PASS |
| Empty lines are ignored and get no reply. | `byte_count` | = 0 | 5 | ❌ FAIL |
| The sketch keeps answering: a later ID? still gets your 9-digit ID. | `text` | matches /^\[0-9\]{9}\\r?\\n$/ | "000851093\\r\\n" | ✅ PASS |

## What to fix

### ❌ ID? ending in \\r\\n also gets your 9-digit ID (the \\r is not part of the command). (`text`)

- **Why:** received "ERR\\r\\n", but expected matches /^\[0-9\]{9}\\r?\\n$/
- **Feedback:** readStringUntil('\\n') only strips the '\\n'; when the line ends in \\r\\n the returned cmd string still has a trailing '\\r', so "ID?\\r" never equals the literal "ID?" and falls into the else branch, printing ERR. Check the comparisons in loop() (lines 27-34) and add a step that trims/strips a trailing '\\r' from cmd before comparing.
- **Where to look:** lf\_only.ino:21

### ❌ HEX? gets your ID in upper-case hex with no leading zeros on one line. (`text`)

- **Why:** received "ERR\\r\\n", but expected matches /^\[1-9A-F\]\[0-9A-F\]{0,7}\\r?\\n$/
- **Feedback:** Same cause as *ID? ending in \\r\\n also gets your 9-digit ID (the \\r is not part of the command).* (`text`). Same root cause as id\_crlf.text: the trailing '\\r' left in cmd makes "HEX?\\r" fail to match "HEX?", so it falls through to ERR.
- **Where to look:** lf\_only.ino:21

### ❌ Empty lines are ignored and get no reply. (`byte_count`)

- **Why:** measured 5, but expected = 0
- **Feedback:** Same cause as *ID? ending in \\r\\n also gets your 9-digit ID (the \\r is not part of the command).* (`text`). An empty line sent as just "\\r\\n" is read by readStringUntil('\\n') as a one-character string "\\r", not an empty string, so the cmd.length()==0 guard on line 23 never triggers; the code falls through to the else branch and sends ERR instead of staying silent. This is caused by the same missing '\\r' handling as the CRLF command checks: the emptiness test needs to run after stripping a trailing '\\r'.
- **Where to look:** lf\_only.ino:23

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
