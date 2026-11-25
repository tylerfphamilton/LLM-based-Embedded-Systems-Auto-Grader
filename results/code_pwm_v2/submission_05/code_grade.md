# Code-only grade: submission_05

> Baseline: claude-sonnet-5 read the code only (no hardware, no measurement).

| Requirement | Verdict | Reason |
|---|---|---|
| The signal on pin D5 must have a frequency of 1 kHz. | PASS | PRESCALER is set to DIV\_16, giving a 16MHz/16 = 1MHz PWM clock (submission\_05.ino comment confirms this). COUNTERTOP is set to 1000, so the period is 1000 ticks / 1MHz = 1ms, i.e. 1kHz, in Up mode where frequency = PWM\_CLK / COUNTERTOP. (pwm\_driver.cpp:16-17) |
| The signal on pin D5 must have a duty cycle of 25%. | PASS | The sequence value is compare \| 0x8000 (PWM\_HIGH=250, PWM\_TOP=1000). On nRF52 PWM, setting the polarity bit (bit15) high makes the output start HIGH for the first \`compare\` ticks of the period and LOW for the remainder, giving a duty cycle of 250/1000 = 25%. (pwm\_driver.cpp:9) |
| The PWM signal on D5 must start automatically after reset without any serial input or button press. | PASS | pwm\_driver\_start() is called unconditionally from setup(), configuring and starting the PWM peripheral (TASKS\_SEQSTART\[0\]=1) with no wait for Serial or button input; loop() is empty, so the signal runs on its own after reset. (submission\_05.ino:18-20) |
| The PWM signal on D5 must be stable (correct frequency and duty cycle) within 50 ms after reset. | PASS | setup() configures the hardware PWM registers and triggers TASKS\_SEQSTART\[0\] immediately, with no delay() or waiting loops beforehand, so the PWM output becomes active and stable almost immediately after reset, well within the 50ms window. (pwm\_driver.cpp:14-27) |
