// pin table lookups (the table is generated: see scripts/gen_pins_h.py)

#include "pins.h"

#include <string.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>

#include "pins_gen.h"

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

// one case per GPIO port the L476RG (LQFP64) has, only if it is enabled in the devicetree
const struct device* pins_port_device(char port){

    switch (port){
#if DT_NODE_HAS_STATUS(DT_NODELABEL(gpioa), okay)
        case 'A': return DEVICE_DT_GET(DT_NODELABEL(gpioa));
#endif
#if DT_NODE_HAS_STATUS(DT_NODELABEL(gpiob), okay)
        case 'B': return DEVICE_DT_GET(DT_NODELABEL(gpiob));
#endif
#if DT_NODE_HAS_STATUS(DT_NODELABEL(gpioc), okay)
        case 'C': return DEVICE_DT_GET(DT_NODELABEL(gpioc));
#endif
#if DT_NODE_HAS_STATUS(DT_NODELABEL(gpiod), okay)
        case 'D': return DEVICE_DT_GET(DT_NODELABEL(gpiod));
#endif
#if DT_NODE_HAS_STATUS(DT_NODELABEL(gpioh), okay)
        case 'H': return DEVICE_DT_GET(DT_NODELABEL(gpioh));
#endif
        default:
            return NULL;
    }
}
