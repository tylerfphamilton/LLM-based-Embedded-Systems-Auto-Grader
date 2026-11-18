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


// Microseconds -> timebase ticks (us up to ~53 s).
uint32_t tb_us_to_ticks(uint32_t us);

// Block the calling thread until tb_now() reaches deadline (a tick value from tb_now()
// plus an offset, at most ~26 s ahead). It sleeps while the deadline is far away, so other
// threads and interrupts keep running, then busy-waits the last stretch, so it returns
// within a fraction of a microsecond of the deadline instead of on a 100 us kernel tick.
// Thread context only.
void tb_wait_until(uint32_t deadline);

#endif