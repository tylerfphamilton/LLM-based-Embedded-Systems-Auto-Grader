/*
 * Lab 3 - Hardware PWM using TIMER2 + GPIOTE + PPI
 *
 * Instead of the PWM peripheral I used a timer with two compare channels
 * and PPI to toggle the pin through GPIOTE, so the CPU is not involved.
 *
 * Pin: D5 = P1.13
 *
 * TIMER2:
 *   16 MHz / 2^4 = 1 MHz  (PRESCALER = 4) -> 1 us per tick
 *   CC[0] = 250   -> toggle (falling edge) at 250 us
 *   CC[1] = 1000  -> toggle (rising edge) at 1000 us = end of period
 *
 * GPIOTE ch0: task mode, toggle, initial level high
 * PPI ch0: TIMER2 COMPARE[0] -> GPIOTE OUT[0]
 * PPI ch1: TIMER2 COMPARE[1] -> GPIOTE OUT[0]
 *
 * High for 250 us out of 1000 us -> 25 % at 1 kHz.
 */

#include <Arduino.h>

#define OUT_PORT    1
#define OUT_PIN     13
#define T_HIGH_US   250
#define T_PERIOD_US 1000

void setup() {
  // GPIOTE channel 0 drives the pin
  NRF_GPIOTE->CONFIG[0] = (GPIOTE_CONFIG_MODE_Task       << GPIOTE_CONFIG_MODE_Pos)     |
                          (OUT_PIN                       << GPIOTE_CONFIG_PSEL_Pos)     |
                          (OUT_PORT                      << GPIOTE_CONFIG_PORT_Pos)     |
                          (GPIOTE_CONFIG_POLARITY_Toggle << GPIOTE_CONFIG_POLARITY_Pos) |
                          (GPIOTE_CONFIG_OUTINIT_High    << GPIOTE_CONFIG_OUTINIT_Pos);

  // Timer setup
  NRF_TIMER2->TASKS_STOP  = 1;
  NRF_TIMER2->TASKS_CLEAR = 1;
  NRF_TIMER2->MODE        = TIMER_MODE_MODE_Timer;
  NRF_TIMER2->BITMODE     = TIMER_BITMODE_BITMODE_16Bit;
  NRF_TIMER2->PRESCALER   = 4;
  NRF_TIMER2->CC[0]       = T_HIGH_US;
  NRF_TIMER2->CC[1]       = T_PERIOD_US;

  // PPI wiring
  NRF_PPI->CH[0].EEP = (uint32_t)&NRF_TIMER2->EVENTS_COMPARE[0];
  NRF_PPI->CH[0].TEP = (uint32_t)&NRF_GPIOTE->TASKS_OUT[0];
  NRF_PPI->CH[1].EEP = (uint32_t)&NRF_TIMER2->EVENTS_COMPARE[1];
  NRF_PPI->CH[1].TEP = (uint32_t)&NRF_GPIOTE->TASKS_OUT[0];
  NRF_PPI->CHENSET   = (1 << 0) | (1 << 1);

  NRF_TIMER2->TASKS_START = 1;
}

void loop() {
}
