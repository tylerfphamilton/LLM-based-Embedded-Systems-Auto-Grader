// Lab 3 - PWM
// Target: 1 kHz, 25% duty, D5 (= P1.13 on the Nano 33 BLE)
//
// PWM_CLK = 16 MHz / 16 = 1 MHz
// COUNTERTOP = 1 MHz / 1 kHz = 1000
// COMPARE    = 0.25 * 1000 = 250
//
// PSEL register layout (from the PS):
//   [4:0]  PIN
//   [5]    PORT
//   [31]   CONNECT
// so pin = 13, port = 1, and the connect bit has to be set.

#include <Arduino.h>

#define D5_PORT   1u
#define D5_PIN    13u
#define TOP       1000u
#define CMP       250u

uint16_t pwmSeq[1];

void setup() {
  pwmSeq[0] = CMP | (1u << 15);

  NRF_PWM0->PSEL.OUT[0] = (D5_PIN  << PWM_PSEL_OUT_PIN_Pos)  |
                          (D5_PORT << PWM_PSEL_OUT_PORT_Pos) |
                          (1u      << PWM_PSEL_OUT_CONNECT_Pos);

  NRF_PWM0->ENABLE     = (PWM_ENABLE_ENABLE_Enabled << PWM_ENABLE_ENABLE_Pos);
  NRF_PWM0->MODE       = (PWM_MODE_UPDOWN_Up << PWM_MODE_UPDOWN_Pos);
  NRF_PWM0->PRESCALER  = (PWM_PRESCALER_PRESCALER_DIV_16 << PWM_PRESCALER_PRESCALER_Pos);
  NRF_PWM0->COUNTERTOP = TOP;
  NRF_PWM0->LOOP       = 0;
  NRF_PWM0->DECODER    = (PWM_DECODER_LOAD_Common << PWM_DECODER_LOAD_Pos) |
                         (PWM_DECODER_MODE_RefreshCount << PWM_DECODER_MODE_Pos);

  NRF_PWM0->SEQ[0].PTR      = (uint32_t)pwmSeq;
  NRF_PWM0->SEQ[0].CNT      = 1;
  NRF_PWM0->SEQ[0].REFRESH  = 0;
  NRF_PWM0->SEQ[0].ENDDELAY = 0;

  NRF_PWM0->TASKS_SEQSTART[0] = 1;
}

void loop() {
}
