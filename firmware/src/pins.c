// Zephyr side of the pin table: port letter -> GPIO device.
// The plain-C lookups (pins_find, pins_wired, ...) are in pins_table.c.

#include "pins.h"

#include <zephyr/device.h>
#include <zephyr/devicetree.h>

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