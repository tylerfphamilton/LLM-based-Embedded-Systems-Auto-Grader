// DELAY implementation: see delay.h.
//
// Both pins get a GPIO edge interrupt (EXTI). The handler reads the TIM5 counter first,
// then decides what the edge means:
//   - before the trigger: a matching edge on from_pin (within the trigger window)
//     becomes the trigger; edges on to_pin are ignored
//   - after the trigger: matching edges on to_pin up to timeout after it are counted, and
//     the time of the first one is kept
// The EXTI watches a pin even while it is an output, so when from_pin is the pin the board
// drives itself (D2 during a DRIVE), the board's own level change is the trigger.
// Both timestamps carry the same interrupt-entry latency (a few us), so it cancels out in
// the delay. A response less than that latency after the trigger can be mis-timed.

#include "delay.h"

#include <zephyr/drivers/gpio.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>

#include "pins.h"
#include "timebase.h"

static const struct device *dev_from, *dev_to;
static uint8_t pin_from, pin_to;
static uint8_t edge_from, edge_to;
static bool same_pin;           // from and to are the same pin (one interrupt for both)
static bool read_level;         // same pin, different edge kinds: the handler reads the level
static struct gpio_callback cb_from, cb_to;
static uint32_t timeout_ticks;
static uint32_t window_ticks;   // how long after the start the trigger may come
static uint32_t started;        // tick when the interrupts were enabled
static bool running;

static volatile bool triggered;
static volatile uint32_t t_trigger, t_first, n_to;
static K_SEM_DEFINE(trigger_sem, 0, 1);

static bool edge_is(uint8_t want, bool rising){
    return want == DELAY_EDGE_ANY || (want == DELAY_EDGE_RISING) == rising;
}

static void on_edge(const struct device *port, struct gpio_callback *c, uint32_t pins){

    uint32_t t = tb_now();      // first thing, like TRACE: keep the latency small and even
    ARG_UNUSED(c);

    bool from = port == dev_from && (pins & BIT(pin_from)) != 0;
    bool to = port == dev_to && (pins & BIT(pin_to)) != 0;
    if (read_level){
        bool rising = gpio_pin_get_raw(port, pin_from) > 0;   // same pin: pin_from == pin_to
        from = from && edge_is(edge_from, rising);
        to = to && edge_is(edge_to, rising);
    }

    if (!triggered){
        if (from && (uint32_t)(t - started) <= window_ticks){
            t_trigger = t;
            triggered = true;
            k_sem_give(&trigger_sem);
        }
        return;     // to_pin edges before the trigger (and the trigger edge itself) don't count
    }
    if (to && (uint32_t)(t - t_trigger) <= timeout_ticks){
        if (n_to == 0){
            t_first = t;
        }
        n_to++;
    }
}

static gpio_flags_t int_flags(uint8_t edges){

    switch (edges){
        case DELAY_EDGE_RISING:     return GPIO_INT_EDGE_RISING;
        case DELAY_EDGE_FALLING:    return GPIO_INT_EDGE_FALLING;
        default:                    return GPIO_INT_EDGE_BOTH;
    }
}

static void stop(void){

    gpio_pin_interrupt_configure(dev_to, pin_to, GPIO_INT_DISABLE);
    if (!same_pin){
        gpio_pin_interrupt_configure(dev_from, pin_from, GPIO_INT_DISABLE);
    }
    gpio_remove_callback(dev_from, &cb_from);
    if (dev_to != dev_from){
        gpio_remove_callback(dev_to, &cb_to);
    }
    running = false;
}

int delay_start(const struct delay_pin *from, const struct delay_pin *to, uint32_t timeout_ms){

    if (running){
        return DELAY_HW;
    }
    dev_from = pins_port_device(from->port);
    dev_to = pins_port_device(to->port);
    if (dev_from == NULL || dev_to == NULL || !device_is_ready(dev_from) || !device_is_ready(dev_to)){
        return DELAY_NO_PORT;
    }
    if (tb_init() != 0){
        return DELAY_HW;
    }

    pin_from = from->pin;
    pin_to = to->pin;
    edge_from = from->edge;
    edge_to = to->edge;
    same_pin = dev_from == dev_to && pin_from == pin_to;

    // one pin watched for both sides: interrupt on every edge either side wants, and tell
    // them apart by the level (only needed when the two sides want different edges)
    uint8_t trig_from = edge_from, trig_to = edge_to;
    if (same_pin){
        trig_from = trig_to = edge_from | edge_to;
    }
    read_level = same_pin && trig_to == DELAY_EDGE_ANY &&
                 !(edge_from == DELAY_EDGE_ANY && edge_to == DELAY_EDGE_ANY);

    // pins the board drives keep their state; inputs get the pull-down, like TRACE, so an
    // undriven pin is a steady 0 instead of noise
    bool keep_from = from->keep || (same_pin && to->keep);
    if (!keep_from && gpio_pin_configure(dev_from, pin_from, GPIO_INPUT | GPIO_PULL_DOWN) != 0){
        return DELAY_HW;
    }
    if (!same_pin && !to->keep && gpio_pin_configure(dev_to, pin_to, GPIO_INPUT | GPIO_PULL_DOWN) != 0){
        return DELAY_HW;
    }

    timeout_ticks = tb_us_to_ticks(timeout_ms * 1000u);
    uint32_t window_ms = timeout_ms > DELAY_TRIGGER_MIN_MS ? timeout_ms : DELAY_TRIGGER_MIN_MS;
    window_ticks = tb_us_to_ticks(window_ms * 1000u);
    triggered = false;
    n_to = 0;
    k_sem_reset(&trigger_sem);

    if (dev_from == dev_to){
        gpio_init_callback(&cb_from, on_edge, BIT(pin_from) | BIT(pin_to));
        if (gpio_add_callback(dev_from, &cb_from) != 0){
            return DELAY_HW;
        }
    }
    else {
        gpio_init_callback(&cb_from, on_edge, BIT(pin_from));
        gpio_init_callback(&cb_to, on_edge, BIT(pin_to));
        if (gpio_add_callback(dev_from, &cb_from) != 0){
            return DELAY_HW;
        }
        if (gpio_add_callback(dev_to, &cb_to) != 0){
            gpio_remove_callback(dev_from, &cb_from);
            return DELAY_HW;
        }
    }

    running = true;
    started = tb_now();
    if (gpio_pin_interrupt_configure(dev_to, pin_to, int_flags(trig_to)) != 0 ||
        (!same_pin && gpio_pin_interrupt_configure(dev_from, pin_from, int_flags(trig_from)) != 0)){
        stop();
        return DELAY_HW;
    }
    return DELAY_OK;
}

int delay_finish(struct delay_raw *out){

    if (!running){
        return DELAY_HW;
    }

    // wait for the trigger, at most the trigger window (the handler refuses a later one)
    int32_t left = (int32_t)(started + window_ticks - tb_now());
    if (!triggered && left > 0){
        uint64_t left_us = ((uint64_t)left * 1000000u) / tb_hz();
        k_sem_take(&trigger_sem, K_USEC(left_us + 1));
    }
    // then count to_pin edges for the full timeout after it
    if (triggered){
        tb_wait_until(t_trigger + timeout_ticks);
    }
    stop();

    unsigned int key = irq_lock();
    bool hit = triggered;
    out->trigger = t_trigger;
    out->first = t_first;
    out->to_count = n_to;
    irq_unlock(key);

    out->clock_hz = tb_hz();
    return hit ? DELAY_OK : DELAY_NO_TRIGGER;
}

void delay_cancel(void){

    if (running){
        stop();
    }
}