// DAC implementation: see dac_out.h.
//
// DAC1 is driven directly with STM32 LL (Zephyr's DAC driver stays disabled, like TIM2 and
// USART1). The channel runs with its output buffer on, so it drives the 1 kOhm wire to the
// student's pin with almost no load error; the cost is that the buffered output only
// reaches about 0.2 V from either rail (STM32L476 datasheet: 0.2 V to VDDA - 0.2 V).
// No trigger is set, so each new value reaches the pin one bus clock after it is written.
//
// The value is mv * 4095 / VDDA, with VDDA (the DAC's full scale, ~3.31 V on the Nucleo)
// measured by the ADC from the internal reference on every call, so the output is in real
// millivolts. If the ADC can't measure it, the DAC assumes 3300 mV.

#include "dac_out.h"
#include "adc_in.h"

#include <stdbool.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/clock_control.h>
#include <zephyr/drivers/clock_control/stm32_clock_control.h>
#include <zephyr/kernel.h>

#include <stm32_ll_bus.h>
#include <stm32_ll_dac.h>
#include <stm32_ll_gpio.h>

#define DAC_NODE        DT_NODELABEL(dac1)
#define SETTLE_US       20      // datasheet settling time for a full-scale step is ~3 us

// STM32 pins with a DAC output (STM32L476 datasheet). PA5 (DAC1_OUT2) also drives the
// Nucleo's green LED (LD2), which would load the output, so it is left out.
struct dac_pin {
    char port;
    uint8_t pin;
    GPIO_TypeDef *gpio;
    uint32_t gpio_clock;
    uint32_t channel;
};

static const struct dac_pin dac_pins[] = {
    {'A', 4, GPIOA, LL_AHB2_GRP1_PERIPH_GPIOA, LL_DAC_CHANNEL_1},   // PA4 = DAC1_OUT1 (Arduino header A2)
};

static bool clock_on;
static bool enabled[sizeof(dac_pins) / sizeof(dac_pins[0])];

int dac_out_set(char port, uint8_t pin, uint32_t mv){

    size_t i = 0;
    while (i < ARRAY_SIZE(dac_pins) && !(dac_pins[i].port == port && dac_pins[i].pin == pin)){
        i++;
    }
    if (i == ARRAY_SIZE(dac_pins)){
        return DAC_OUT_NO_CHANNEL;
    }
    const struct dac_pin *p = &dac_pins[i];

    if (!clock_on){
        static const struct stm32_pclken clocks[] = STM32_DT_CLOCKS(DAC_NODE);
        const struct device *clk = DEVICE_DT_GET(STM32_CLOCK_CONTROL_NODE);
        if (!device_is_ready(clk) || clock_control_on(clk, (clock_control_subsys_t)&clocks[0]) != 0){
            return DAC_OUT_HW;
        }
        clock_on = true;
    }

    uint32_t vdda = adc_in_vdda_mv();
    if (vdda == 0){
        vdda = DAC_OUT_MAX_MV;
    }
    // rounded; asking for more than VDDA gives full scale
    uint32_t code = mv >= vdda ? 4095u : (mv * 4095u + vdda / 2) / vdda;

    if (!enabled[i]){
        // first use: the pin becomes an analog pin (no digital input or output stage), the
        // channel gets its output buffer, and the value is loaded before the output turns
        // on so it starts at the requested level
        LL_AHB2_GRP1_EnableClock(p->gpio_clock);
        LL_GPIO_SetPinMode(p->gpio, 1u << p->pin, LL_GPIO_MODE_ANALOG);
        LL_DAC_ConfigOutput(DAC1, p->channel, LL_DAC_OUTPUT_MODE_NORMAL,
                            LL_DAC_OUTPUT_BUFFER_ENABLE, LL_DAC_OUTPUT_CONNECT_GPIO);
        LL_DAC_DisableTrigger(DAC1, p->channel);
        LL_DAC_ConvertData12RightAligned(DAC1, p->channel, code);
        LL_DAC_Enable(DAC1, p->channel);
        k_busy_wait(LL_DAC_DELAY_STARTUP_VOLTAGE_SETTLING_US);
        enabled[i] = true;
    }
    LL_DAC_ConvertData12RightAligned(DAC1, p->channel, code);
    k_busy_wait(SETTLE_US);
    return DAC_OUT_OK;
}