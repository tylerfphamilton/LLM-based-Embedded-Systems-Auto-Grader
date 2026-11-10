/*
 * Lab 3: Hardware PWM
 *
 * Uses NRF_PWM1 to output 1 kHz @ 25% on D5 (P1.13).
 *
 * Calculations:
 *   base clock      = 16 MHz
 *   prescaler       = DIV_16  -> f_pwm = 1 MHz (1 us per count)
 *   counter runs from 0 up to TOP-1 and then wraps, so
 *   number of counts per period = 1000 -> TOP = 1000 - 1 = 999
 *   duty            = 25% * 1000 counts = 250 counts
 *
 * Sequence word: [15] polarity (1 = high while counter < compare),
 *                [14:0] compare value
 */

#include <Arduino.h>

const uint32_t kPort      = 1;
const uint32_t kPin       = 13;
const uint16_t kCountsPer = 1000;
const uint16_t kTop       = kCountsPer - 1;
const uint16_t kCompare   = kCountsPer / 4;

uint16_t seqBuf[1] = { (uint16_t)(kCompare | (1u << 15)) };

void startPwm() {
  NRF_PWM_Type *pwm = NRF_PWM1;

  pwm->PSEL.OUT[0] = (kPort << PWM_PSEL_OUT_PORT_Pos) | (kPin << PWM_PSEL_OUT_PIN_Pos);
  pwm->ENABLE      = (PWM_ENABLE_ENABLE_Enabled << PWM_ENABLE_ENABLE_Pos);
  pwm->MODE        = (PWM_MODE_UPDOWN_Up << PWM_MODE_UPDOWN_Pos);
  pwm->PRESCALER   = (PWM_PRESCALER_PRESCALER_DIV_16 << PWM_PRESCALER_PRESCALER_Pos);
  pwm->COUNTERTOP  = kTop;
  pwm->LOOP        = 0;
  pwm->DECODER     = (PWM_DECODER_LOAD_Common << PWM_DECODER_LOAD_Pos) |
                     (PWM_DECODER_MODE_RefreshCount << PWM_DECODER_MODE_Pos);

  pwm->SEQ[0].PTR      = (uint32_t)&seqBuf[0];
  pwm->SEQ[0].CNT      = 1;
  pwm->SEQ[0].REFRESH  = 0;
  pwm->SEQ[0].ENDDELAY = 0;

  pwm->TASKS_SEQSTART[0] = 1;
}

void setup() {
  startPwm();
}

void loop() {
}
