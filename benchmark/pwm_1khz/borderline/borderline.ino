// Target: Arduino Nano 33 BLE Sense, Arduino mbed core (arduino:mbed_nano:nano33ble).
// 1 kHz, 25% duty PWM on D5 using the nRF52840 hardware PWM through mbed::PwmOut.

#include "mbed.h"

const uint32_t PERIOD_US = 981;  // ~1 ms period -> ~1 kHz
const float DUTY = 0.25f;        // 25% high time

mbed::PwmOut pwm(digitalPinToPinName(D5));

void setup() {
  pwm.period_us(PERIOD_US);
  pwm.write(DUTY);
}

void loop() {
  // Nothing to do: the PWM peripheral runs on its own.
}
