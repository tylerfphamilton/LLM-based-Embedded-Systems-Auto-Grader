#include "pwm_driver.h"
#include <Arduino.h>

// Sequence buffer for EasyDMA. Only one value since we use Common load mode.
static uint16_t s_seq[1];

void pwm_driver_start(uint8_t port, uint8_t pin, uint16_t top, uint16_t compare) {
  // bit 15 = polarity, makes compare the active-high time
  s_seq[0] = compare | 0x8000;

  NRF_PWM0->PSEL.OUT[0] = ((uint32_t)port << PWM_PSEL_OUT_PORT_Pos) |
                          ((uint32_t)pin  << PWM_PSEL_OUT_PIN_Pos);

  NRF_PWM0->ENABLE     = PWM_ENABLE_ENABLE_Enabled << PWM_ENABLE_ENABLE_Pos;
  NRF_PWM0->MODE       = PWM_MODE_UPDOWN_Up << PWM_MODE_UPDOWN_Pos;
  NRF_PWM0->PRESCALER  = PWM_PRESCALER_PRESCALER_DIV_16 << PWM_PRESCALER_PRESCALER_Pos;
  NRF_PWM0->COUNTERTOP = top;
  NRF_PWM0->LOOP       = 0;
  NRF_PWM0->DECODER    = (PWM_DECODER_LOAD_Common << PWM_DECODER_LOAD_Pos) |
                         (PWM_DECODER_MODE_RefreshCount << PWM_DECODER_MODE_Pos);

  NRF_PWM0->SEQ[0].PTR      = (uint32_t)s_seq;
  NRF_PWM0->SEQ[0].CNT      = sizeof(s_seq);
  NRF_PWM0->SEQ[0].REFRESH  = 0;
  NRF_PWM0->SEQ[0].ENDDELAY = 0;

  NRF_PWM0->TASKS_SEQSTART[0] = 1;
}
