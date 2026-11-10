#ifndef PWM_DRIVER_H
#define PWM_DRIVER_H

#include <stdint.h>

// Configure PWM0 for a fixed-frequency, fixed-duty output on one pin.
//   port/pin  : nRF GPIO port and pin number
//   top       : COUNTERTOP value (period in PWM clock ticks)
//   compare   : high time in PWM clock ticks
void pwm_driver_start(uint8_t port, uint8_t pin, uint16_t top, uint16_t compare);

#endif
