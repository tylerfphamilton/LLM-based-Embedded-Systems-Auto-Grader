// Timer input capture with TIM2 (32-bit), set up with STM32 LL calls.
//
// One input pin feeds two capture channels:
//   CH1 = TI1, rising edges   (CCMR1 CC1S = direct)
//   CH2 = TI1, falling edges  (CCMR1 CC2S = indirect: IC2 is mapped on TI1)
// The timer free-runs at the full timer clock, so each edge's timestamp is latched by the
// hardware the moment it happens. The interrupt only reads the latched value, so interrupt
// latency does not change the measurement (it only limits how fast edges may come).
//
// TIM2 belongs to this file: app.overlay disables the board's default PWM on TIM2.

#include "capture.h"

#include <stdbool.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/clock_control.h>
#include <zephyr/drivers/clock_control/stm32_clock_control.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>

#include <stm32_ll_bus.h>
#include <stm32_ll_gpio.h>
#include <stm32_ll_tim.h>

#define CAP_TIM_NODE DT_NODELABEL(timers2)
#define CAP_TIM      ((TIM_TypeDef *)DT_REG_ADDR(CAP_TIM_NODE))
#define CAP_IRQ      DT_IRQN(CAP_TIM_NODE)

// STM32 pins that can be routed to TIM2 channel 1 (STM32L476 datasheet, alternate functions).
// PA5 is also TIM2_CH1 but drives the Nucleo's green LED (LD2), so it is left out.
struct capture_input {
    char port;
    uint8_t pin;
    GPIO_TypeDef *gpio;
    uint32_t af;
};

static const struct capture_input inputs[] = {
    {'A', 0, GPIOA, LL_GPIO_AF_1},   // PA0  = TIM2_CH1 (Arduino header A0)
    {'A', 15, GPIOA, LL_GPIO_AF_1},  // PA15 = TIM2_CH1 (morpho header; free when using SWD)
};

static volatile struct capture_raw acc;  // filled by the interrupt during a window
static volatile bool rise_open;          // a rising edge was seen and its falling edge not yet
static uint32_t tim_clk_hz;
static bool initialized;

static void on_rise(uint32_t t){

    if (acc.rising == 0){
        acc.first_rise = t;
    }
    acc.last_rise = t;
    acc.rising++;
    rise_open = true;
}

static void on_fall(uint32_t t){

    acc.falling++;
    // only pulses whose rising edge was seen count towards the duty cycle
    // (the window may start in the middle of a high phase)
    if (rise_open){
        acc.high_ticks += (uint32_t)(t - acc.last_rise);   // unsigned subtraction handles wrap
        acc.high_count++;
        rise_open = false;
    }
}

static void cap_isr(const void *arg){

    ARG_UNUSED(arg);
    TIM_TypeDef *tim = CAP_TIM;
    uint32_t sr = tim->SR;
    bool rise = (sr & TIM_SR_CC1IF) != 0;
    bool fall = (sr & TIM_SR_CC2IF) != 0;

    // reading CCRx also clears its CCxIF flag
    uint32_t t_rise = rise ? tim->CCR1 : 0;
    uint32_t t_fall = fall ? tim->CCR2 : 0;

    // a capture arrived while the previous one was still unread: an edge was lost
    if (sr & (TIM_SR_CC1OF | TIM_SR_CC2OF)){
        acc.overruns++;
        tim->SR = ~(TIM_SR_CC1OF | TIM_SR_CC2OF);   // rc_w0: writing 0 clears, 1 leaves as is
    }

    // both edges pending (short pulse): handle them in the order they happened
    if (rise && fall && (int32_t)(t_fall - t_rise) < 0){
        on_fall(t_fall);
        on_rise(t_rise);
    }
    else {
        if (rise){
            on_rise(t_rise);
        }
        if (fall){
            on_fall(t_fall);
        }
    }
}

// turn on the TIM2 clock, read its rate and hook up its interrupt (once)
static int capture_init(void){

    static const struct stm32_pclken clocks[] = STM32_DT_CLOCKS(CAP_TIM_NODE);
    const struct device *clk = DEVICE_DT_GET(STM32_CLOCK_CONTROL_NODE);

    if (!device_is_ready(clk)){
        return CAPTURE_HW;
    }
    // clocks[0] = bus clock gate (APB1), clocks[1] = timer kernel clock (TIMPCLK1)
    if (clock_control_on(clk, (clock_control_subsys_t)&clocks[0]) != 0){
        return CAPTURE_HW;
    }
    if (clock_control_get_rate(clk, (clock_control_subsys_t)&clocks[1], &tim_clk_hz) != 0){
        return CAPTURE_HW;
    }

    IRQ_CONNECT(CAP_IRQ, DT_IRQ(CAP_TIM_NODE, priority), cap_isr, NULL, 0);
    irq_enable(CAP_IRQ);
    initialized = true;
    return CAPTURE_OK;
}

int capture_measure(char port, uint8_t pin, uint32_t window_ms, struct capture_raw *out){

    const struct capture_input *in = NULL;
    for (size_t i = 0; i < sizeof(inputs) / sizeof(inputs[0]); i++){
        if (inputs[i].port == port && inputs[i].pin == pin){
            in = &inputs[i];
        }
    }
    if (in == NULL){
        return CAPTURE_NO_TIMER;
    }
    if (!initialized){
        int rc = capture_init();
        if (rc != CAPTURE_OK){
            return rc;
        }
    }

    TIM_TypeDef *tim = CAP_TIM;
    uint32_t mask = 1u << in->pin;   // LL_GPIO_PIN_n == (1 << n)

    // fresh accumulators (the interrupt is off, so no race)
    acc = (struct capture_raw){0};
    rise_open = false;

    // route the pin to the timer: alternate function, no pull resistor
    LL_AHB2_GRP1_EnableClock(LL_AHB2_GRP1_PERIPH_GPIOA);
    LL_GPIO_SetPinPull(in->gpio, mask, LL_GPIO_PULL_NO);
    if (in->pin < 8){
        LL_GPIO_SetAFPin_0_7(in->gpio, mask, in->af);
    }
    else {
        LL_GPIO_SetAFPin_8_15(in->gpio, mask, in->af);
    }
    LL_GPIO_SetPinMode(in->gpio, mask, LL_GPIO_MODE_ALTERNATE);

    // free-running 32-bit counter at the full timer clock (wraps after ~53 s at 80 MHz)
    LL_TIM_DisableCounter(tim);
    LL_TIM_SetCounterMode(tim, LL_TIM_COUNTERMODE_UP);
    LL_TIM_SetPrescaler(tim, 0);
    LL_TIM_SetAutoReload(tim, UINT32_MAX);
    LL_TIM_GenerateEvent_UPDATE(tim);   // load the prescaler now

    // CH1: rising edges of TI1. The filter ignores glitches shorter than 4 clocks (50 ns);
    // it sits on TI1, so it applies to both channels
    LL_TIM_IC_SetActiveInput(tim, LL_TIM_CHANNEL_CH1, LL_TIM_ACTIVEINPUT_DIRECTTI);
    LL_TIM_IC_SetPolarity(tim, LL_TIM_CHANNEL_CH1, LL_TIM_IC_POLARITY_RISING);
    LL_TIM_IC_SetPrescaler(tim, LL_TIM_CHANNEL_CH1, LL_TIM_ICPSC_DIV1);
    LL_TIM_IC_SetFilter(tim, LL_TIM_CHANNEL_CH1, LL_TIM_IC_FILTER_FDIV1_N4);

    // CH2: falling edges of the same input (TI1)
    LL_TIM_IC_SetActiveInput(tim, LL_TIM_CHANNEL_CH2, LL_TIM_ACTIVEINPUT_INDIRECTTI);
    LL_TIM_IC_SetPolarity(tim, LL_TIM_CHANNEL_CH2, LL_TIM_IC_POLARITY_FALLING);
    LL_TIM_IC_SetPrescaler(tim, LL_TIM_CHANNEL_CH2, LL_TIM_ICPSC_DIV1);

    tim->SR = 0;
    NVIC_ClearPendingIRQ(CAP_IRQ);
    LL_TIM_CC_EnableChannel(tim, LL_TIM_CHANNEL_CH1 | LL_TIM_CHANNEL_CH2);
    LL_TIM_EnableIT_CC1(tim);
    LL_TIM_EnableIT_CC2(tim);
    LL_TIM_EnableCounter(tim);

    // the hardware does the timing; this thread just sleeps through the window
    k_msleep((int32_t)window_ms);

    LL_TIM_DisableIT_CC1(tim);
    LL_TIM_DisableIT_CC2(tim);
    LL_TIM_DisableCounter(tim);
    LL_TIM_CC_DisableChannel(tim, LL_TIM_CHANNEL_CH1 | LL_TIM_CHANNEL_CH2);
    NVIC_ClearPendingIRQ(CAP_IRQ);

    unsigned int key = irq_lock();
    *out = acc;
    irq_unlock(key);
    out->clock_hz = tim_clk_hz;

    // release the pin: plain input again (high impedance)
    LL_GPIO_SetPinMode(in->gpio, mask, LL_GPIO_MODE_INPUT);
    return CAPTURE_OK;
}