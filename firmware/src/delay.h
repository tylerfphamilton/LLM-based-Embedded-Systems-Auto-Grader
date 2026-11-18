// DELAY: time from an edge on one pin (the trigger) to the response edge on another.
// Plain C header (no Zephyr includes) so cmd.c can still be compiled and tested on a PC;
// the implementation in delay.c is Zephyr code.
#ifndef GRADER_DELAY_H
#define GRADER_DELAY_H

#include <stdbool.h>
#include <stdint.h>

// which edges count (a bit mask: ANY = RISING | FALLING)
enum {
    DELAY_EDGE_RISING = 1,
    DELAY_EDGE_FALLING = 2,
    DELAY_EDGE_ANY = 3,
};

// delay_* return codes
enum {
    DELAY_OK = 0,
    DELAY_NO_PORT = -1,     // a pin's GPIO port doesn't exist or isn't enabled
    DELAY_HW = -2,          // timebase, pin or edge interrupt could not be set up
    DELAY_NO_TRIGGER = -3,  // from_pin never made its edge in the trigger window (a rig fault)
};

// The trigger may come up to max(timeout_ms, DELAY_TRIGGER_MIN_MS) after the start, so a
// short timeout still catches a slow periodic trigger (a 2 Hz blink). The reply then takes
// at most 1000 ms + 2 x timeout_ms, inside the host's 2 s + 1.5 x timeout_ms.
#define DELAY_TRIGGER_MIN_MS 1000u

// one side of the measurement
struct delay_pin {
    char port;      // STM32 port letter
    uint8_t pin;    // pin number within the port
    uint8_t edge;   // DELAY_EDGE_*
    bool keep;      // true for a pin the board drives: leave it as it is (driven or
                    // released) instead of making it an input with the pull-down
};

// raw result. Timestamps are timebase ticks at clock_hz
struct delay_raw {
    uint32_t clock_hz;
    uint32_t trigger;    // tick of the trigger edge on from_pin
    uint32_t first;      // tick of the first matching edge on to_pin (valid if to_count > 0)
    uint32_t to_count;   // matching edges on to_pin from the trigger until timeout after it
};

// Start watching: from now on, the first matching edge on `from` within the trigger window
// (see DELAY_TRIGGER_MIN_MS) is the trigger, and matching edges on `to` up to timeout_ms
// after the trigger are counted. Returns at once. One measurement at a time.
int delay_start(const struct delay_pin *from, const struct delay_pin *to, uint32_t timeout_ms);

// Block until the measurement is over (no trigger within the trigger window, or
// timeout_ms after the trigger), stop watching and fill *out. DELAY_NO_TRIGGER if the
// trigger never came.
int delay_finish(struct delay_raw *out);

// Stop a running measurement without a result (RESET). Does nothing if none is running.
void delay_cancel(void);

#endif