// PLACEHOLDER for the real benchmark: a minimal stand-in so LLM feedback has code to read.
// Scenario: scenarios/pwm/wrong_pin.yaml. Planted bug: the PWM is on D6 instead of D5,
// so D5 shows no signal at all.
// Target: Arduino Nano 33 BLE Sense, Arduino mbed core (arduino:mbed_nano:nano33ble).

#include "mbed.h"

const uint32_t BASE_CLOCK_HZ = 16000000;  // PWM peripheral clock
const uint32_t PRESCALER = 16;            // 16 MHz / 16 = 1 MHz tick
const uint32_t COUNTER_TOP = 1000;        // 1 ms period -> 1 kHz
const float DUTY = 0.25f;                 // 25% high time
const int PWM_PIN = D6;

mbed::PwmOut pwm(digitalPinToPinName(PWM_PIN));

void setup() {
  const uint32_t period_us = (uint64_t)PRESCALER * COUNTER_TOP * 1000000 / BASE_CLOCK_HZ;
  pwm.period_us(period_us);
  pwm.write(DUTY);
}

void loop() {
  // Nothing to do: the PWM peripheral runs on its own.
}
