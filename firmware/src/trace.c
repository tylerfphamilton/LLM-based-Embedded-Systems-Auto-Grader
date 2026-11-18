// TRACE implementation: GPIO edge interrupt + shared timebase. See trace.h.
//
// The interrupt handler only reads the TIM5 counter and stores it, so each timestamp is
// late by the interrupt entry time (a few microseconds), the same for every edge. That is
// far below what TRACE is used for (LED blinks, button responses: milliseconds). Edges
// closer together than that latency can be missed.

#include "trace.h"

#include <zephyr/drivers/gpio.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>

#include "pins.h"
#include "timebase.h"

static struct gpio_callback cb;
static uint32_t *buf;                 // the caller's t[] while a window runs
static volatile uint32_t count;       // every edge
static volatile uint32_t stored;      // edges written to buf

static void on_edge(const struct device *port, struct gpio_callback *c, uint32_t pins){

    ARG_UNUSED(port);
    ARG_UNUSED(c);
    ARG_UNUSED(pins);

    uint32_t t = tb_now();    // first thing: keep the latency as small and as even as possible
    if (stored < TRACE_MAX_EDGES){
        buf[stored++] = t;
    }
    count++;
}

int trace_measure(char port, uint8_t pin, uint32_t window_ms, struct trace_raw *out){

    const struct device *gpio = pins_port_device(port);
    if (gpio == NULL || !device_is_ready(gpio)){
        return TRACE_NO_PORT;
    }
    if (tb_init() != 0){
        return TRACE_HW;
    }

    // input with the internal pull-down, like FREQ: an undriven pin reads as a steady 0
    // instead of picking up noise as edges
    if (gpio_pin_configure(gpio, pin, GPIO_INPUT | GPIO_PULL_DOWN) != 0){
        return TRACE_HW;
    }

    buf = out->t;
    count = 0;
    stored = 0;

    gpio_init_callback(&cb, on_edge, BIT(pin));
    if (gpio_add_callback(gpio, &cb) != 0){
        return TRACE_HW;
    }

    out->start = tb_now();
    if (gpio_pin_interrupt_configure(gpio, pin, GPIO_INT_EDGE_BOTH) != 0){
        gpio_remove_callback(gpio, &cb);
        return TRACE_HW;
    }

    k_msleep((int32_t)window_ms);

    gpio_pin_interrupt_configure(gpio, pin, GPIO_INT_DISABLE);
    gpio_remove_callback(gpio, &cb);

    unsigned int key = irq_lock();
    out->edge_count = count;
    out->stored = stored;
    irq_unlock(key);

    out->final_level = gpio_pin_get_raw(gpio, pin) > 0 ? 1 : 0;
    out->clock_hz = tb_hz();
    return TRACE_OK;
}