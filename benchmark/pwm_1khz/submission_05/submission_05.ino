// Lab 3 - Hardware PWM
//
// Output: D5 (P1.13), 1 kHz, 25 % duty
//
// PWM clock  = 16 MHz / 16 = 1 MHz
// COUNTERTOP = 1,000,000 / 1,000 = 1000 ticks
// compare    = 1000 * 0.25 = 250 ticks
//
// Driver code is in pwm_driver.cpp so it can be reused in later labs.

#include "pwm_driver.h"

#define OUT_PORT   1
#define OUT_PIN    13
#define PWM_TOP    1000
#define PWM_HIGH   250

void setup() {
  pwm_driver_start(OUT_PORT, OUT_PIN, PWM_TOP, PWM_HIGH);
}

void loop() {
}
