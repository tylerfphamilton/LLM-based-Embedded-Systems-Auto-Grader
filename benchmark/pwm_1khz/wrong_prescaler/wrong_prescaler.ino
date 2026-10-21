// PLACEHOLDER for the real benchmark: a minimal stand-in so LLM feedback has code to read.
// Scenario: scenarios/pwm/wrong_prescaler.yaml. Planted bug: the prescaler is twice too
// large, so the period is 2 ms and D5 runs at 500 Hz (duty is still 25%).
// Target: Arduino Nano 33 BLE Sense, Arduino mbed core (arduino:mbed_nano:nano33ble).

#include "mbed.h"

const uint32_t BASE_CLOCK_HZ = 16000000;  // PWM peripheral clock
const uint32_t PRESCALER = 32;            // 16 MHz / 32 = 500 kHz tick
const uint32_t COUNTER_TOP = 1000;        // 1000 ticks per period
const float DUTY = 0.25f;                 // 25% high time

mbed::PwmOut pwm(digitalPinToPinName(D5));

void setup() {
  const uint32_t period_us = (uint64_t)PRESCALER * COUNTER_TOP * 1000000 / BASE_CLOCK_HZ;
  pwm.period_us(period_us);
  pwm.write(DUTY);
}

void loop() {
  // Nothing to do: the PWM peripheral runs on its own.
}
