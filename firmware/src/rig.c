// Rig actions that need Zephyr: see rig.h.

#include "rig.h"

#include <errno.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>

#include "pins.h"

void rig_sleep_ms(uint32_t ms){
    k_sleep(K_MSEC(ms));
}

int rig_reset_pulse(char port, uint8_t pin){

    const struct device* gpio = pins_port_device(port);
    if (gpio == NULL || !device_is_ready(gpio)){
        return -ENODEV;
    }

    // open-drain output, starting released (high = not driven). Configuring it every time
    // is cheap and means nothing has to happen at boot: until the first RESET the pin is
    // in its reset state (high impedance), which also leaves the student board running.
    int rc = gpio_pin_configure(gpio, pin, GPIO_OUTPUT_HIGH | GPIO_OPEN_DRAIN);
    if (rc != 0){
        return rc;
    }

    // exactly one pulse: two resets within about half a second put the Nano 33 BLE into
    // its bootloader (the "double tap"), and the student's sketch would not run
    gpio_pin_set_raw(gpio, pin, 0);    // pull RST low: student board held in reset
    k_sleep(K_MSEC(RIG_RESET_PULSE_MS));
    gpio_pin_set_raw(gpio, pin, 1);    // release: its pull-up brings RST high, it boots
    return 0;
}