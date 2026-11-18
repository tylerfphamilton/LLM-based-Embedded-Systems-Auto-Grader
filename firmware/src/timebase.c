// Shared timebase on TIM5: see timebase.h.
//
// TIM5 is the STM32L476's other 32-bit timer. On this 64-pin package all four of its
// channel pins (PA0-PA3) are taken (D5 capture, RST, host UART), so it runs with no pins
// at all: just a counter that every other module reads.

#include "timebase.h"

#include <errno.h>
#include <stdbool.h>
#include <zephyr/kernel.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/clock_control.h>
#include <zephyr/drivers/clock_control/stm32_clock_control.h>

#include <stm32_ll_tim.h>

#define TB_NODE DT_NODELABEL(timers5)
#define TB_TIM  ((TIM_TypeDef *)DT_REG_ADDR(TB_NODE))

static uint32_t hz;
static bool running;

int tb_init(void){

    if (running){
        return 0;
    }

    // clocks[0] = bus clock gate (APB1), clocks[1] = timer kernel clock (TIMPCLK1)
    static const struct stm32_pclken clocks[] = STM32_DT_CLOCKS(TB_NODE);
    const struct device *clk = DEVICE_DT_GET(STM32_CLOCK_CONTROL_NODE);

    if (!device_is_ready(clk)){
        return -ENODEV;
    }
    if (clock_control_on(clk, (clock_control_subsys_t)&clocks[0]) != 0){
        return -EIO;
    }
    if (clock_control_get_rate(clk, (clock_control_subsys_t)&clocks[1], &hz) != 0){
        return -EIO;
    }

    TIM_TypeDef *tim = TB_TIM;
    LL_TIM_DisableCounter(tim);
    LL_TIM_SetCounterMode(tim, LL_TIM_COUNTERMODE_UP);
    LL_TIM_SetPrescaler(tim, 0);              // one tick per timer clock (12.5 ns at 80 MHz)
    LL_TIM_SetAutoReload(tim, UINT32_MAX);    // full 32-bit range
    LL_TIM_SetCounter(tim, 0);
    LL_TIM_GenerateEvent_UPDATE(tim);         // load the prescaler now
    LL_TIM_ClearFlag_UPDATE(tim);
    LL_TIM_EnableCounter(tim);

    running = true;
    return 0;
}

uint32_t tb_now(void){
    return LL_TIM_GetCounter(TB_TIM);
}

uint32_t tb_hz(void){
    return hz;
}


uint32_t tb_us_to_ticks(uint32_t us){
    return (uint32_t)(((uint64_t)us * hz) / 1000000u);
}

void tb_wait_until(uint32_t deadline){

    if (hz == 0){
        return;    // timebase not running: nothing to wait on
    }

    // ticks still to go; signed, so a deadline already in the past returns at once
    int32_t left;
    while ((left = (int32_t)(deadline - tb_now())) > 0){
        uint64_t left_us = ((uint64_t)left * 1000000u) / hz;
        if (left_us > 1000){
            // far away: sleep, but wake up ~0.5 ms early (the kernel tick is 100 us and
            // a sleep can end up to one tick late)
            k_sleep(K_USEC(left_us - 500));
        }
        // close: spin on the counter
    }
}