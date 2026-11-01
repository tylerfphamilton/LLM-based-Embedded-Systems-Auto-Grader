/*
 * GENERATED FILE - DO NOT EDIT.
 * Source: config/pinmap.yaml
 * Regenerate: python scripts/gen_pins_h.py   (check: --check)
 */
#ifndef GRADER_PINS_GEN_H
#define GRADER_PINS_GEN_H

#include "pins.h"

/* First 8 hex chars of SHA-256 of the canonical pin map (host: pinmap_hash). */
#define PINMAP_HASH "ceff724f"

#define CAP_GPIO          (1u << 0)
#define CAP_DRIVE         (1u << 1)
#define CAP_TIMER_CAPTURE (1u << 2)
#define CAP_UART_RX       (1u << 3)
#define CAP_UART_TX       (1u << 4)
#define CAP_ANALOG_IN     (1u << 5)
#define CAP_DAC           (1u << 6)
#define CAP_I2C_SDA       (1u << 7)
#define CAP_I2C_SCL       (1u << 8)
#define CAP_RESET         (1u << 9)

/* name, port letter (0 = not wired), pin number, capabilities */
static const struct pin_def PINS[] = {
    { "A0", 0, 0, CAP_ANALOG_IN | CAP_DAC },
    { "A4", 0, 0, CAP_I2C_SDA },
    { "A5", 0, 0, CAP_I2C_SCL },
    { "D0", 'A', 9, CAP_UART_TX },
    { "D1", 'A', 10, CAP_UART_RX },
    { "D13", 0, 0, CAP_GPIO | CAP_TIMER_CAPTURE },
    { "D2", 0, 0, CAP_GPIO | CAP_DRIVE },
    { "D5", 'A', 0, CAP_GPIO | CAP_TIMER_CAPTURE },
    { "RST", 0, 0, CAP_RESET },
};

#define PINS_COUNT 9

#endif
