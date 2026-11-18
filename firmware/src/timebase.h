// Shared timebase: TIM5 as a free-running 32-bit counter at the timer clock (80 MHz).
// Every event that has to be compared with another (drive edges, traced edges, delays)
// is stamped with tb_now(), so time between events is a plain unsigned subtraction.
// The counter wraps every ~53 s at 80 MHz; windows are at most 10 s, so (later - earlier)
// in uint32_t arithmetic is always right.
// Plain C header (no Zephyr includes); the implementation is timebase.c.
#ifndef GRADER_TIMEBASE_H
#define GRADER_TIMEBASE_H

#include <stdint.h>

// Start the counter (once; later calls do nothing). Returns 0, or a negative errno if the
// timer clock could not be set up.
int tb_init(void);

// Current counter value (ticks). Cheap enough to call from an interrupt handler.
uint32_t tb_now(void);

// Tick rate in Hz (0 until tb_init succeeds).
uint32_t tb_hz(void);

#endif