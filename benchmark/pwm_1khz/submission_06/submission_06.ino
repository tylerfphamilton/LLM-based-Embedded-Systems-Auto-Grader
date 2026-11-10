/*
  Lab 3 - Hardware PWM
  1 kHz square wave, 25% duty, on D5.

  D5 = P1.13

  PWM peripheral clock: 16 MHz
  PRESCALER = DIV_16 -> 1 MHz, 1 us resolution
  COUNTERTOP = 1000  -> 1000 us period = 1 kHz
  compare    = 250   -> 250 us high = 25 %

  The duty value is constant so I made the table const.
*/

#include <Arduino.h>

static const uint16_t PWM_TABLE[] = { 250 | 0x8000 };

void setup() {
  NRF_PWM3->PSEL.OUT[0] = (1UL << PWM_PSEL_OUT_PORT_Pos) | (13UL << PWM_PSEL_OUT_PIN_Pos);

  NRF_PWM3->ENABLE     = PWM_ENABLE_ENABLE_Enabled;
  NRF_PWM3->MODE       = PWM_MODE_UPDOWN_Up;
  NRF_PWM3->PRESCALER  = PWM_PRESCALER_PRESCALER_DIV_16;
  NRF_PWM3->COUNTERTOP = 1000;
  NRF_PWM3->LOOP       = 0;
  NRF_PWM3->DECODER    = (PWM_DECODER_LOAD_Common << PWM_DECODER_LOAD_Pos) |
                         (PWM_DECODER_MODE_RefreshCount << PWM_DECODER_MODE_Pos);

  NRF_PWM3->SEQ[0].PTR      = (uint32_t)PWM_TABLE;
  NRF_PWM3->SEQ[0].CNT      = sizeof(PWM_TABLE) / sizeof(PWM_TABLE[0]);
  NRF_PWM3->SEQ[0].REFRESH  = 0;
  NRF_PWM3->SEQ[0].ENDDELAY = 0;

  NRF_PWM3->TASKS_SEQSTART[0] = 1;
}

void loop() {
}
