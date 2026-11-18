// TRACE: record the edges on one pin over a window.
// Plain C header (no Zephyr includes) so cmd.c can still be compiled and tested on a PC;
// the implementation in trace.c is Zephyr code.
#ifndef GRADER_TRACE_H
#define GRADER_TRACE_H

#include <stdbool.h>
#include <stdint.h>

// Edges stored per window. A reply line only has room for ~90 timestamps anyway; edges
// beyond this are still counted in edge_count.
#define TRACE_MAX_EDGES 256

// raw result of one window. Timestamps are timebase ticks at clock_hz
struct trace_raw {
    uint32_t clock_hz;               // timebase tick rate
    uint32_t start;                  // tick when the window started
    uint32_t edge_count;             // every edge seen, rising and falling
    uint32_t stored;                 // how many of them are in t[] (at most TRACE_MAX_EDGES)
    uint32_t t[TRACE_MAX_EDGES];     // tick of each stored edge, in order
    uint8_t final_level;             // pin level (0/1) at the end of the window
};

// trace_* return codes
enum {
    TRACE_OK = 0,
    TRACE_NO_PORT = -1,     // the pin's GPIO port doesn't exist or isn't enabled
    TRACE_HW = -2,          // timebase, pin or edge interrupt could not be set up
};

// Start recording edges on STM32 pin P<port><pin> for window_ms into *out; returns at once.
// Edges are timestamped in an interrupt. keep = true for a pin the board drives itself:
// leave it as it is (driven or released) instead of making it an input with the
// pull-down, so TRACE can watch the board's own DRIVE. One window at a time; *out must
// stay valid until trace_finish.
int trace_start(char port, uint8_t pin, bool keep, uint32_t window_ms, struct trace_raw *out);

// Block until the window ends, stop and complete *out.
int trace_finish(void);

// Stop a running window without a result (RESET). Does nothing if none is running.
void trace_cancel(void);

#endif