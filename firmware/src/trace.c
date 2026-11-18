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
static const struct device *dev;      // the running window's port and pin
static uint8_t pin_no;
static struct trace_raw *result;      // the caller's result, completed by trace_finish
static uint32_t window_end;           // timebase tick when the window ends
static bool running;

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

static void stop(void){

    gpio_pin_interrupt_configure(dev, pin_no, GPIO_INT_DISABLE);
    gpio_remove_callback(dev, &cb);
    running = false;
}

int trace_start(char port, uint8_t pin, bool keep, uint32_t window_ms, struct trace_raw *out){

    if (running){
        return TRACE_HW;        // one window at a time (cmd.c reports BUSY before this)
    }
    const struct device *gpio = pins_port_device(port);
    if (gpio == NULL || !device_is_ready(gpio)){
        return TRACE_NO_PORT;
    }
    if (tb_init() != 0){
        return TRACE_HW;
    }

    // input with the internal pull-down, like FREQ: an undriven pin reads as a steady 0
    // instead of picking up noise as edges. A pin the board drives is left as it is.
    if (!keep && gpio_pin_configure(gpio, pin, GPIO_INPUT | GPIO_PULL_DOWN) != 0){
        return TRACE_HW;
    }

    dev = gpio;
    pin_no = pin;
    result = out;
    buf = out->t;
    count = 0;
    stored = 0;

    gpio_init_callback(&cb, on_edge, BIT(pin));
    if (gpio_add_callback(gpio, &cb) != 0){
        return TRACE_HW;
    }

    out->start = tb_now();
    window_end = out->start + tb_us_to_ticks(window_ms * 1000u);
    if (gpio_pin_interrupt_configure(gpio, pin, GPIO_INT_EDGE_BOTH) != 0){
        gpio_remove_callback(gpio, &cb);
        return TRACE_HW;
    }
    running = true;
    return TRACE_OK;
}

int trace_finish(void){

    if (!running){
        return TRACE_HW;
    }
    tb_wait_until(window_end);
    stop();

    unsigned int key = irq_lock();
    result->edge_count = count;
    result->stored = stored;
    irq_unlock(key);

    result->final_level = gpio_pin_get_raw(dev, pin_no) > 0 ? 1 : 0;
    result->clock_hz = tb_hz();
    return TRACE_OK;
}

void trace_cancel(void){

    if (running){
        stop();
    }
}