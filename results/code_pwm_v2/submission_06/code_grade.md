# Code-only grade: submission_06

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The signal on pin D5 must have a frequency of 1 kHz. | PASS | PRESCALER = DIV\_16 yields a 1MHz PWM clock (1us ticks) and COUNTERTOP = 1000 gives a 1000us period in Up-counter mode, producing exactly 1kHz. (submission\_06.ino:24-25) |
| The signal on pin D5 must have a duty cycle of 25%. | FAIL | The compare value 250 \| 0x8000 sets the nRF52 PWM polarity bit (bit 15), which inverts which portion of the period is active. This makes the output LOW for the first 250us and HIGH for the remaining 750us, giving an actual duty cycle of 75% HIGH instead of the intended 25%, contradicting the student's own comment. (submission\_06.ino:17) |
| The PWM signal on D5 must start automatically after reset without any serial input or button press. | PASS | setup() configures the PWM peripheral and immediately issues TASKS\_SEQSTART\[0\] = 1 with no wait for Serial input or button press, and loop() is empty, so the signal starts automatically after reset. (submission\_06.ino:35) |
| The PWM signal on D5 must be stable (correct frequency and duty cycle) within 50 ms after reset. | FAIL | Although the PWM registers are configured synchronously in setup() with no delays (so timing is well within 50ms), the polarity bit error (0x8000) means the duty cycle is never actually 25% — it is stably wrong at ~75%, so the signal never reaches the correct frequency+duty state required. (submission\_06.ino:17) |
