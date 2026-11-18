// Timer input capture on one STM32 pin: counts edges and times them over a window.
// Plain C header (no Zephyr includes) so cmd.c can still be compiled and tested on a PC;
// the implementation in capture.c is Zephyr + STM32 LL code.
#ifndef GRADER_CAPTURE_H
#define GRADER_CAPTURE_H

#include <stdint.h>

// raw result of one capture window. Timestamps are timer ticks at clock_hz
struct capture_raw {
    uint32_t clock_hz;      // timer tick rate (80 MHz with the default clock tree)
    uint32_t rising;        // rising edges seen in the window
    uint32_t falling;       // falling edges seen in the window
    uint32_t first_rise;    // tick of the first rising edge
    uint32_t last_rise;     // tick of the last rising edge
    uint64_t high_ticks;    // summed high time of every pulse whose rising edge was seen
    uint32_t high_count;    // number of pulses summed in high_ticks
    uint32_t overruns;      // edges lost because they came faster than the interrupt read them
};

// capture_* return codes
enum {
    CAPTURE_OK = 0,
    CAPTURE_NO_TIMER = -1,  // this STM32 pin can't be routed to the capture timer
    CAPTURE_HW = -2,        // timer clock could not be set up
};

// Start capturing both edges on STM32 pin P<port><pin> for window_ms; returns at once.
// The edges are timed in hardware. One window at a time.
int capture_start(char port, uint8_t pin, uint32_t window_ms);

// Block until the window ends, stop and fill *out.
int capture_finish(struct capture_raw *out);

// Stop a running window without a result (RESET). Does nothing if none is running.
void capture_cancel(void);

#endif