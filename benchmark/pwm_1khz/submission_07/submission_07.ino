// Lab 3 -- 1kHz 25% PWM on D5 with the PWM peripheral
//
// pin:  D5 is P1.13 -> PSEL port 1, pin 13
// clk:  16MHz / 16 = 1MHz
// top:  1MHz / 1kHz = 1000
// duty: 1000 / 4 = 250, OR'd with 0x8000 for active-high
//
// seq A = SEQ[0], seq B = SEQ[1]. only one sequence needed.

#include <Arduino.h>

uint16_t duty_seq[] = { 250 | 0x8000 };

void pwm_init(void) {
  NRF_PWM0->PSEL.OUT[0] = (1 << PWM_PSEL_OUT_PORT_Pos) | (13 << PWM_PSEL_OUT_PIN_Pos);
  NRF_PWM0->ENABLE      = PWM_ENABLE_ENABLE_Enabled << PWM_ENABLE_ENABLE_Pos;
  NRF_PWM0->MODE        = PWM_MODE_UPDOWN_Up << PWM_MODE_UPDOWN_Pos;
  NRF_PWM0->PRESCALER   = PWM_PRESCALER_PRESCALER_DIV_16 << PWM_PRESCALER_PRESCALER_Pos;
  NRF_PWM0->COUNTERTOP  = 1000;
  NRF_PWM0->LOOP        = 0;
  NRF_PWM0->DECODER     = (PWM_DECODER_LOAD_Common << PWM_DECODER_LOAD_Pos) |
                          (PWM_DECODER_MODE_RefreshCount << PWM_DECODER_MODE_Pos);

  NRF_PWM0->SEQ[0].PTR      = (uint32_t)duty_seq;
  NRF_PWM0->SEQ[0].CNT      = 1;
  NRF_PWM0->SEQ[0].REFRESH  = 0;
  NRF_PWM0->SEQ[0].ENDDELAY = 0;
}

void pwm_start(void) {
  NRF_PWM0->TASKS_SEQSTART[1] = 1;
}

void setup() {
  pwm_init();
  pwm_start();
}

void loop() {
}
