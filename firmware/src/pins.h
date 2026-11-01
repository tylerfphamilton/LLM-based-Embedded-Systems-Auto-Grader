// pin table lookups: student-board pin names (from the plan) -> STM32 port and pin
// The table itself is generated from config/pinmap.yaml into pins_gen.h
#ifndef GRADER_PINS_H
#define GRADER_PINS_H

#include <stdbool.h>
#include <stdint.h>

// one row of the generated pin table
struct pin_def {
    const char* name;   // student-board name, e.g. "D5"
    char port;          // STM32 port letter 'A', 'B', ... or 0 if not wired (TBD in the pin map)
    uint8_t pin;        // pin number within the port (0-15)
    uint32_t caps;      // CAP_* bits from pins_gen.h
};

// declared here so this header stays free of Zephyr includes
struct device;

// pin-map hash compiled into this firmware (PINMAP_HASH from pins_gen.h), reported by PING
extern const char pins_map_hash[];

// returns the table row for a student-board pin name, or NULL if the name is unknown
const struct pin_def* pins_find(const char* name);

// true if the pin is wired to a real STM32 pin
bool pins_wired(const struct pin_def* p);

// returns the Zephyr GPIO device for a port letter, or NULL if the port doesn't exist or isn't enabled
const struct device* pins_port_device(char port);

#endif
