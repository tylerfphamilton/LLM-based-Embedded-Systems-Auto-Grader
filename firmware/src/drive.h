// DRIVE: the STM32 acts as the student's input (a button, a switch, a logic signal).
// Plain C header (no Zephyr includes) so cmd.c can still be compiled and tested on a PC;
// the implementation in drive.c is Zephyr + STM32 LL code.
#ifndef GRADER_DRIVE_H
#define GRADER_DRIVE_H

#include <stdint.h>

// levels a pin can be driven to
enum {
    DRIVE_LOW = 0,
    DRIVE_HIGH = 1,
    DRIVE_RELEASE = 2,      // input with no pull: the student board's pull-up/down decides
};

// drive_* return codes
enum {
    DRIVE_OK = 0,
    DRIVE_NO_PORT = -1,     // the pin's GPIO port doesn't exist or isn't enabled
    DRIVE_HW = -2,          // the pin could not be configured
};

// Drive STM32 pin P<port><pin> HIGH or LOW (push-pull output), or RELEASE it.
// Every pin starts released at boot.
int drive_set(char port, uint8_t pin, int level);

// Drive the pin to level (HIGH/LOW) for width_ms, then put it back the way it was
// (driven high, driven low, or released). Blocks for width_ms.
int drive_pulse(char port, uint8_t pin, int level, uint32_t width_ms);

// Switch bounce: exactly `count` level changes, interval_us apart, the last one leaving
// the pin at final_level (HIGH/LOW). The first change happens at once; if count is odd the
// pin starts at the opposite of final_level, if even at final_level (so a released pin
// pulled high, bounced with an odd count to LOW, gives no extra edge). Each change is
// scheduled on the timebase, so timing errors do not add up. Blocks for
// (count - 1) * interval_us.
int drive_bounce(char port, uint8_t pin, uint32_t count, uint32_t interval_us, int final_level);

#endif