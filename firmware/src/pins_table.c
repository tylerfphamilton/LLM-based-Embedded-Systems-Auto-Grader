// pin table lookups (the table is generated: see scripts/gen_pins_h.py)
// Plain C (no Zephyr includes) so cmd.c can be compiled and tested on a PC with the real
// lookups. The Zephyr-specific part (port letter -> GPIO device) is in pins.c.

#include "pins.h"
#include "pins_gen.h"
#include <string.h>


const char pins_map_hash[] = PINMAP_HASH;

const struct pin_def* pins_find(const char* name){

    for (size_t i = 0; i < PINS_COUNT; i++){
        if (strcmp(PINS[i].name, name) == 0){
            return &PINS[i];
        }
    }
    return NULL;
}

bool pins_wired(const struct pin_def* p){
    return p != NULL && p->port != 0;
}

bool pins_can_capture(const struct pin_def* p){
    return p != NULL && (p->caps & CAP_TIMER_CAPTURE) != 0;
}

bool pins_is_gpio(const struct pin_def* p){
    return p != NULL && (p->caps & CAP_GPIO) != 0;
}

bool pins_can_drive(const struct pin_def* p){
    return p != NULL && (p->caps & CAP_DRIVE) != 0;
}

const struct pin_def* pins_reset_line(void){

    for (size_t i = 0; i < PINS_COUNT; i++){
        if (PINS[i].caps & CAP_RESET){
            return &PINS[i];
        }
    }
    return NULL;
}


// first row with the capability, or NULL
static const struct pin_def* first_with(uint32_t cap){

    for (size_t i = 0; i < PINS_COUNT; i++){
        if (PINS[i].caps & cap){
            return &PINS[i];
        }
    }
    return NULL;
}

const struct pin_def* pins_uart_rx_line(void){
    return first_with(CAP_UART_RX);
}

const struct pin_def* pins_uart_tx_line(void){
    return first_with(CAP_UART_TX);
}