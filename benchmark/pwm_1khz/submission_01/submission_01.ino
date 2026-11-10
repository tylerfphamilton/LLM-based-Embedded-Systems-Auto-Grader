// Lab 3 - Hardware PWM
// 1 kHz, 25% duty on D5 using the nRF52840 PWM0 peripheral.
//
// D5 on the Nano 33 BLE Sense is P1.13 (from the schematic).
//
// PWM clock = 16 MHz / 16 = 1 MHz  ->  1 tick = 1 us
// Period for 1 kHz = 1000 us = 1000 ticks -> COUNTERTOP = 1000
// I used center-aligned (up/down) mode so the edges are symmetric
// around the middle of the period, which gives a cleaner waveform.
// 25% of 1000 = 250 ticks high.
// Bit 15 of the sequence value sets polarity so the compare value
// is the HIGH time instead of the LOW time.

#include <Arduino.h>

#define PWM_PORT        1
#define PWM_PIN         13
#define PWM_TOP         1000
#define PWM_DUTY_TICKS  250

static uint16_t pwm_seq[1];

void setup() {
  pwm_seq[0] = PWM_DUTY_TICKS | 0x8000;

  NRF_PWM0->PSEL.OUT[0] = (PWM_PORT << PWM_PSEL_OUT_PORT_Pos) |
                          (PWM_PIN  << PWM_PSEL_OUT_PIN_Pos);

  NRF_PWM0->ENABLE     = PWM_ENABLE_ENABLE_Enabled << PWM_ENABLE_ENABLE_Pos;
  NRF_PWM0->MODE       = PWM_MODE_UPDOWN_UpAndDown << PWM_MODE_UPDOWN_Pos;
  NRF_PWM0->PRESCALER  = PWM_PRESCALER_PRESCALER_DIV_16 << PWM_PRESCALER_PRESCALER_Pos;
  NRF_PWM0->COUNTERTOP = PWM_TOP;
  NRF_PWM0->LOOP       = 0;
  NRF_PWM0->DECODER    = (PWM_DECODER_LOAD_Common << PWM_DECODER_LOAD_Pos) |
                         (PWM_DECODER_MODE_RefreshCount << PWM_DECODER_MODE_Pos);

  NRF_PWM0->SEQ[0].PTR      = (uint32_t)pwm_seq;
  NRF_PWM0->SEQ[0].CNT      = 1;
  NRF_PWM0->SEQ[0].REFRESH  = 0;
  NRF_PWM0->SEQ[0].ENDDELAY = 0;

  NRF_PWM0->TASKS_SEQSTART[0] = 1;
}

void loop() {
  // nothing to do, PWM runs in hardware
}
