// PLACEHOLDER for the real benchmark: a minimal stand-in so LLM feedback has code to read.
// Scenario: scenarios/pwm/correct.yaml (reference solution, no bug).
// Target: Arduino Nano 33 BLE Sense, Arduino mbed core (arduino:mbed_nano:nano33ble).
//
// 1 kHz, 25% duty PWM on D5 using the nRF52840 hardware PWM through mbed::PwmOut.

#include "mbed.h"

const uint32_t BASE_CLOCK_HZ = 16000000;  // PWM peripheral clock
const uint32_t PRESCALER = 16;            // 16 MHz / 16 = 1 MHz tick
const uint32_t COUNTER_TOP = 1000;        // 1000 ticks at 1 MHz = 1 ms period -> 1 kHz
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
