// Lab 3 - Hardware PWM, D5, 1 kHz, 25%
//
// D5 = P1.13
// PWM clock 16 MHz, DIV_16 -> 1 MHz
// COUNTERTOP = 1000 (1 ms period)
// compare = 250 (0.25 ms high)
//
// Prints the register values on startup so I can check them.

#include <Arduino.h>

#define PWM_TOP   1000
#define PWM_CMP   250

static uint16_t seq0[1] = { PWM_CMP | 0x8000 };

void setup() {
  Serial.begin(115200);
  while (!Serial) { }

  NRF_PWM0->PSEL.OUT[0] = (1 << PWM_PSEL_OUT_PORT_Pos) | (13 << PWM_PSEL_OUT_PIN_Pos);
  NRF_PWM0->ENABLE      = PWM_ENABLE_ENABLE_Enabled << PWM_ENABLE_ENABLE_Pos;
  NRF_PWM0->MODE        = PWM_MODE_UPDOWN_Up << PWM_MODE_UPDOWN_Pos;
  NRF_PWM0->PRESCALER   = PWM_PRESCALER_PRESCALER_DIV_16 << PWM_PRESCALER_PRESCALER_Pos;
  NRF_PWM0->COUNTERTOP  = PWM_TOP;
  NRF_PWM0->LOOP        = 0;
  NRF_PWM0->DECODER     = (PWM_DECODER_LOAD_Common << PWM_DECODER_LOAD_Pos) |
                          (PWM_DECODER_MODE_RefreshCount << PWM_DECODER_MODE_Pos);
  NRF_PWM0->SEQ[0].PTR      = (uint32_t)seq0;
  NRF_PWM0->SEQ[0].CNT      = 1;
  NRF_PWM0->SEQ[0].REFRESH  = 0;
  NRF_PWM0->SEQ[0].ENDDELAY = 0;
  NRF_PWM0->TASKS_SEQSTART[0] = 1;

  Serial.print("COUNTERTOP = ");
  Serial.println(NRF_PWM0->COUNTERTOP);
  Serial.print("PRESCALER  = ");
  Serial.println(NRF_PWM0->PRESCALER);
  Serial.print("SEQ0       = 0x");
  Serial.println(seq0[0], HEX);
}

void loop() {
}
