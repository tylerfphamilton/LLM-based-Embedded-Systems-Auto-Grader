// Rig actions that need Zephyr or the hardware: sleeping, and driving the student board's
// reset line. Plain C header (no Zephyr includes) so cmd.c can still be compiled and tested
// on a PC; the implementation is in rig.c, and the PC test harness provides stand-ins.
#ifndef GRADER_RIG_H
#define GRADER_RIG_H

#include <stdint.h>

// how long RESET holds the student board's RST line low
#define RIG_RESET_PULSE_MS 10

// Sleep the calling thread for ms milliseconds. Interrupts (and the measurements they run)
// keep going while it sleeps.
void rig_sleep_ms(uint32_t ms);

// One reset pulse on STM32 pin P<port><pin>: pull it low for RIG_RESET_PULSE_MS, then
// release it. The pin is open-drain, so it only ever pulls low or floats; the student
// board's own pull-up holds RST high. Returns 0, or a negative errno if the GPIO port is
// missing or can't be configured.
int rig_reset_pulse(char port, uint8_t pin);

#endif