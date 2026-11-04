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