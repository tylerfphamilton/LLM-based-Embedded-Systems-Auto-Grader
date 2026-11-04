/*
 * Lab 2 - PWM output
 * Square wave on pin D5: 1 kHz, high for a quarter of each period.
 */
#include <mbed.h>

#define OUT_PIN D5
#define HIGH_TIME_US 250

static mbed::PwmOut *wave = nullptr;

static void startWave() {
  wave = new mbed::PwmOut(digitalPinToPinName(OUT_PIN));
  wave->period_ms(1);                  // 1 ms -> 1000 Hz
  wave->pulsewidth_us(HIGH_TIME_US);   // 250 us of 1000 us = 25 %
}

void setup() {
  startWave();
}

void loop() {
  delay(1000);
}
