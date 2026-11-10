// ECE Lab 3 - hardware PWM on D5
//
// D5 -> P1.13
// I compute the register values from the clock so I don't hardcode magic numbers.
//
//   CORE_CLK   = 64 MHz (nRF52840 runs at 64 MHz)
//   PRESCALER  = 16  -> 64 MHz / 16 = 4 MHz tick
//   TOP        = 4 MHz / 1 kHz = 4000
//   DUTY       = TOP / 4 = 1000  (25%)
//
// TOP fits in the 15-bit COUNTERTOP register (max 32767).

#include <Arduino.h>

#define CORE_CLK_HZ   64000000UL
#define PRESC_DIV     16UL
#define TARGET_HZ     1000UL

#define PWM_TOP_VAL   (CORE_CLK_HZ / PRESC_DIV / TARGET_HZ)
#define PWM_DUTY_VAL  (PWM_TOP_VAL / 4)

static uint16_t seq_values[] = { (uint16_t)(PWM_DUTY_VAL | 0x8000) };

void setup() {
  NRF_PWM2->PSEL.OUT[0] = (1 << PWM_PSEL_OUT_PORT_Pos) | (13 << PWM_PSEL_OUT_PIN_Pos);
  NRF_PWM2->PSEL.OUT[1] = PWM_PSEL_OUT_CONNECT_Disconnected << PWM_PSEL_OUT_CONNECT_Pos;
  NRF_PWM2->PSEL.OUT[2] = PWM_PSEL_OUT_CONNECT_Disconnected << PWM_PSEL_OUT_CONNECT_Pos;
  NRF_PWM2->PSEL.OUT[3] = PWM_PSEL_OUT_CONNECT_Disconnected << PWM_PSEL_OUT_CONNECT_Pos;

  NRF_PWM2->ENABLE     = 1;
  NRF_PWM2->MODE       = PWM_MODE_UPDOWN_Up;
  NRF_PWM2->PRESCALER  = PWM_PRESCALER_PRESCALER_DIV_16;
  NRF_PWM2->COUNTERTOP = PWM_TOP_VAL;
  NRF_PWM2->LOOP       = 0;
  NRF_PWM2->DECODER    = PWM_DECODER_LOAD_Common | (PWM_DECODER_MODE_RefreshCount << PWM_DECODER_MODE_Pos);

  NRF_PWM2->SEQ[0].PTR      = (uint32_t)seq_values;
  NRF_PWM2->SEQ[0].CNT      = 1;
  NRF_PWM2->SEQ[0].REFRESH  = 0;
  NRF_PWM2->SEQ[0].ENDDELAY = 0;

  NRF_PWM2->TASKS_SEQSTART[0] = 1;
}

void loop() {}
