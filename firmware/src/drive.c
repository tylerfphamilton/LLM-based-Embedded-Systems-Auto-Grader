// DRIVE implementation: see drive.h.
//
// Pins are configured with the Zephyr GPIO API (which also turns on the port clock), and
// the fast level changes inside BOUNCE use STM32 LL writes to the port's set/reset register,
// so each change is a single store at the moment its deadline comes.
//
// Wiring: every driven line goes through a 1 kOhm series resistor. If the student's sketch
// also drives the same pin, the two outputs fight; the resistor limits that to ~3.3 mA.

#include "drive.h"

#include <stdbool.h>
#include <zephyr/drivers/gpio.h>
#include <zephyr/kernel.h>

#include <stm32_ll_gpio.h>

#include "pins.h"
#include "timebase.h"

// what the firmware is doing with each pin it has driven (pins start released)
struct pin_state {
    char port;      // 0 = unused slot
    uint8_t pin;
    int level;      // DRIVE_LOW / DRIVE_HIGH / DRIVE_RELEASE
};

#define MAX_DRIVEN 8
static struct pin_state states[MAX_DRIVEN];

static struct pin_state *state_of(char port, uint8_t pin){

    struct pin_state *free_slot = NULL;
    for (size_t i = 0; i < MAX_DRIVEN; i++){
        if (states[i].port == port && states[i].pin == pin){
            return &states[i];
        }
        if (states[i].port == 0 && free_slot == NULL){
            free_slot = &states[i];
        }
    }
    if (free_slot != NULL){
        *free_slot = (struct pin_state){port, pin, DRIVE_RELEASE};
    }
    return free_slot;   // NULL only if more than MAX_DRIVEN pins are ever driven
}

static GPIO_TypeDef *ll_port(char port){

    switch (port){
        case 'A': return GPIOA;
        case 'B': return GPIOB;
        case 'C': return GPIOC;
        case 'D': return GPIOD;
        case 'H': return GPIOH;
        default:  return NULL;
    }
}

// configure the pin for `level`; going to HIGH/LOW sets the output level before the pin
// becomes an output, so there is no glitch
static int apply(const struct device *gpio, struct pin_state *st, int level){

    gpio_flags_t flags;
    switch (level){
        case DRIVE_HIGH:    flags = GPIO_OUTPUT_HIGH; break;
        case DRIVE_LOW:     flags = GPIO_OUTPUT_LOW;  break;
        default:            flags = GPIO_INPUT;       break;
    }
    if (gpio_pin_configure(gpio, st->pin, flags) != 0){
        return DRIVE_HW;
    }
    st->level = level;
    return DRIVE_OK;
}

static int lookup(char port, uint8_t pin, const struct device **gpio, struct pin_state **st){

    *gpio = pins_port_device(port);
    if (*gpio == NULL || !device_is_ready(*gpio) || ll_port(port) == NULL){
        return DRIVE_NO_PORT;
    }
    *st = state_of(port, pin);
    return *st == NULL ? DRIVE_HW : DRIVE_OK;
}

int drive_set(char port, uint8_t pin, int level){

    const struct device *gpio;
    struct pin_state *st;
    int rc = lookup(port, pin, &gpio, &st);
    if (rc != DRIVE_OK){
        return rc;
    }
    return apply(gpio, st, level);
}

int drive_pulse(char port, uint8_t pin, int level, uint32_t width_ms){

    const struct device *gpio;
    struct pin_state *st;
    int rc = lookup(port, pin, &gpio, &st);
    if (rc != DRIVE_OK){
        return rc;
    }
    if (tb_init() != 0){
        return DRIVE_HW;
    }

    int before = st->level;
    rc = apply(gpio, st, level);
    if (rc != DRIVE_OK){
        return rc;
    }
    uint32_t start = tb_now();
    tb_wait_until(start + tb_us_to_ticks(width_ms * 1000u));
    return apply(gpio, st, before);
}

int drive_bounce(char port, uint8_t pin, uint32_t count, uint32_t interval_us, int final_level){

    const struct device *gpio;
    struct pin_state *st;
    int rc = lookup(port, pin, &gpio, &st);
    if (rc != DRIVE_OK){
        return rc;
    }
    if (tb_init() != 0 || count == 0){
        return DRIVE_HW;
    }

    // starting level: after `count` changes the pin must be at final_level
    int level = (count % 2 == 1) ? !final_level : final_level;
    rc = apply(gpio, st, level);
    if (rc != DRIVE_OK){
        return rc;
    }

    GPIO_TypeDef *port_regs = ll_port(port);
    uint32_t mask = 1u << pin;                 // LL_GPIO_PIN_n == (1 << n)
    uint32_t step = tb_us_to_ticks(interval_us);
    uint32_t deadline = tb_now();              // first change at once

    for (uint32_t i = 0; i < count; i++){
        tb_wait_until(deadline);
        level = !level;
        if (level){
            LL_GPIO_SetOutputPin(port_regs, mask);
        }
        else {
            LL_GPIO_ResetOutputPin(port_regs, mask);
        }
        deadline += step;                      // from the last deadline, not from "now"
    }
    st->level = level;                         // == final_level
    return DRIVE_OK;
}