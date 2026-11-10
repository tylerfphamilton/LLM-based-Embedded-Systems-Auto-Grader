// Lab 3 - Hardware PWM
// D5 (P1.13), 1 kHz, 25 % duty, NRF_PWM0
//
// PWM clock  : 16 MHz / 16 (DIV_16)  = 1 MHz
// COUNTERTOP : 1 MHz / 1 kHz         = 1000
// compare    : 25 % of 1000          = 250
// polarity   : bit 15 set so 250 is the high time

#include <Arduino.h>

static uint16_t seq[1] = { 250 | 0x8000 };

void setup() {
  NRF_PWM0->PSEL.OUT[0] = (1 << PWM_PSEL_OUT_PORT_Pos) | (13 << PWM_PSEL_OUT_PIN_Pos);
  NRF_PWM0->ENABLE      = PWM_ENABLE_ENABLE_Enabled << PWM_ENABLE_ENABLE_Pos;
  NRF_PWM0->MODE        = PWM_MODE_UPDOWN_Up << PWM_MODE_UPDOWN_Pos;
  NRF_PWM0->PRESCALER   = PWM_PRESCALER_PRESCALER_DIV_16 << PWM_PRESCALER_PRESCALER_Pos;
  NRF_PWM0->COUNTERTOP  = 1000;
  NRF_PWM0->LOOP        = 0;
  NRF_PWM0->DECODER     = (PWM_DECODER_LOAD_Common << PWM_DECODER_LOAD_Pos) |
                          (PWM_DECODER_MODE_RefreshCount << PWM_DECODER_MODE_Pos);
  NRF_PWM0->SEQ[0].PTR      = (uint32_t)seq;
  NRF_PWM0->SEQ[0].CNT      = 1;
  NRF_PWM0->SEQ[0].REFRESH  = 0;
  NRF_PWM0->SEQ[0].ENDDELAY = 0;
  NRF_PWM0->TASKS_SEQSTART[0] = 1;
}

void loop() {
}
