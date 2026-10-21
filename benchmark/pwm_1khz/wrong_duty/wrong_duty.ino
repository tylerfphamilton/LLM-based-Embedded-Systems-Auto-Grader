// PLACEHOLDER for the real benchmark: a minimal stand-in so LLM feedback has code to read.
// Scenario: scenarios/pwm/wrong_duty.yaml. Planted bug: the compare value is set to half
// the period, so the duty cycle is 50% instead of 25% (frequency is correct).
// Target: Arduino Nano 33 BLE Sense, Arduino mbed core (arduino:mbed_nano:nano33ble).

#include "mbed.h"

const uint32_t BASE_CLOCK_HZ = 16000000;  // PWM peripheral clock
const uint32_t PRESCALER = 16;            // 16 MHz / 16 = 1 MHz tick
const uint32_t COUNTER_TOP = 1000;        // 1 ms period -> 1 kHz
const uint32_t COMPARE = COUNTER_TOP / 2; // ticks the output stays high

mbed::PwmOut pwm(digitalPinToPinName(D5));

void setup() {
  const uint32_t period_us = (uint64_t)PRESCALER * COUNTER_TOP * 1000000 / BASE_CLOCK_HZ;
  pwm.period_us(period_us);
  pwm.write((float)COMPARE / COUNTER_TOP);
}

void loop() {
  // Nothing to do: the PWM peripheral runs on its own.
}
