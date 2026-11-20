# Autograder report: button_toggle_opus_b

**Submission:** `wrong_baud`  
**Result: 0 of 16 checks passed** · 0 failed · 0 borderline · 16 could not be measured

> Debounced button toggle: button on D2 (active low, INPUT_PULLUP) toggles the LED on D13 once per bouncy press and prints ON/OFF on Serial1 at 9600 baud.

| Requirement | Quantity | Expected | Measured | Verdict |
|---|---|---|---|---|
| The LED is off after reset. | `final_level` | = 0 | — | 🛠️ RIG ERROR |
| The LED is off after reset. | `edge_count` | = 0 | — | 🛠️ RIG ERROR |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `delay_ms` | any value (not null) | — | 🛠️ RIG ERROR |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | — | 🛠️ RIG ERROR |
| The first bouncy press turns the LED on exactly once, within 100 ms. | `to_edge_count` | = 1 | — | 🛠️ RIG ERROR |
| The first press prints ON on its own line on Serial1. | `text` | matches /^ON\\r?\\n$/ | — | 🛠️ RIG ERROR |
| The first press prints ON on its own line on Serial1. | `framing_errors` | = 0 | — | 🛠️ RIG ERROR |
| Releasing the button does not change the LED (it stays on). | `edge_count` | = 0 | — | 🛠️ RIG ERROR |
| Releasing the button does not change the LED (it stays on). | `final_level` | = 1 | — | 🛠️ RIG ERROR |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | any value (not null) | — | 🛠️ RIG ERROR |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `delay_ms` | ≤ 100 ms | — | 🛠️ RIG ERROR |
| The second bouncy press turns the LED off exactly once, within 100 ms. | `to_edge_count` | = 1 | — | 🛠️ RIG ERROR |
| The second press prints OFF on its own line on Serial1. | `text` | matches /^OFF\\r?\\n$/ | — | 🛠️ RIG ERROR |
| The second press prints OFF on its own line on Serial1. | `framing_errors` | = 0 | — | 🛠️ RIG ERROR |
| Releasing the button again leaves the LED off. | `edge_count` | = 0 | — | 🛠️ RIG ERROR |
| Releasing the button again leaves the LED off. | `final_level` | = 0 | — | 🛠️ RIG ERROR |

## Not measured: test equipment problem

These checks could not be measured because of a problem with the test rig. They do **not** count against you; they will be re-run.

- **The LED is off after reset.** (`final_level`)
- **The LED is off after reset.** (`edge_count`)
- **The first bouncy press turns the LED on exactly once, within 100 ms.** (`delay_ms`)
- **The first bouncy press turns the LED on exactly once, within 100 ms.** (`delay_ms`)
- **The first bouncy press turns the LED on exactly once, within 100 ms.** (`to_edge_count`)
- **The first press prints ON on its own line on Serial1.** (`text`)
- **The first press prints ON on its own line on Serial1.** (`framing_errors`)
- **Releasing the button does not change the LED (it stays on).** (`edge_count`)
- **Releasing the button does not change the LED (it stays on).** (`final_level`)
- **The second bouncy press turns the LED off exactly once, within 100 ms.** (`delay_ms`)
- **The second bouncy press turns the LED off exactly once, within 100 ms.** (`delay_ms`)
- **The second bouncy press turns the LED off exactly once, within 100 ms.** (`to_edge_count`)
- **The second press prints OFF on its own line on Serial1.** (`text`)
- **The second press prints OFF on its own line on Serial1.** (`framing_errors`)
- **Releasing the button again leaves the LED off.** (`edge_count`)
- **Releasing the button again leaves the LED off.** (`final_level`)

## Not graded automatically

- **Implement debouncing in software, without blocking delay() calls.**: The pins can't show how the debouncing is done. Only its effect (one toggle per press, fast response) is tested.
- **Comment your code.**: Code style can't be observed electrically.

## Assumptions the grader made

- The handout gives no number for 'quickly', so the LED must change within 100 ms of the first press edge, which is about where people start to notice a delay.
- A bouncy press is 5 edges 200 us apart, ending LOW (pressed).
- Releasing the button is the board letting go of D2, so the student's INPUT\_PULLUP pulls it high.
- Serial lines may end with \\n or \\r\\n.
- Releasing the button must not toggle the LED (only presses do).
