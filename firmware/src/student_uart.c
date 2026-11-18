// UART implementation: see student_uart.h.
//
// USART1 is driven directly with STM32 LL (the overlay disables Zephyr's driver for it),
// so the firmware sees every flag of every byte: a byte with a framing error is still
// received and counted, which is what tells a wrong-baud sketch apart from a silent one.
//
// Clock: the USART runs from the 80 MHz bus clock (crystal-locked, so the baud is exact).
// Its divider is 16 bits, so below ~1221 baud (300, 1200) it switches to the 16 MHz
// internal RC oscillator (HSI16, about +-1%: fine for a UART, which tolerates ~4%).

#include "student_uart.h"

#include <stdbool.h>
#include <string.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/clock_control.h>
#include <zephyr/drivers/clock_control/stm32_clock_control.h>
#include <zephyr/irq.h>
#include <zephyr/kernel.h>

#include <stm32_ll_bus.h>
#include <stm32_ll_gpio.h>
#include <stm32_ll_rcc.h>
#include <stm32_ll_usart.h>

#include "timebase.h"

#define SU_NODE   DT_NODELABEL(usart1)
#define SU_USART  ((USART_TypeDef *)DT_REG_ADDR(SU_NODE))
#define SU_IRQ    DT_IRQN(SU_NODE)
#define HSI16_HZ  16000000u

// STM32 pins that can be routed to USART1 (STM32L476 datasheet, alternate function 7)
struct su_pin {
    char port;
    uint8_t pin;
    GPIO_TypeDef *gpio;
    uint32_t gpio_clock;
};

static const struct su_pin tx_pins[] = {
    {'A', 9, GPIOA, LL_AHB2_GRP1_PERIPH_GPIOA},     // PA9 = USART1_TX (Arduino header D8)
    {'B', 6, GPIOB, LL_AHB2_GRP1_PERIPH_GPIOB},     // PB6 = USART1_TX (Arduino header D10)
};
static const struct su_pin rx_pins[] = {
    {'A', 10, GPIOA, LL_AHB2_GRP1_PERIPH_GPIOA},    // PA10 = USART1_RX (Arduino header D2)
    {'B', 7, GPIOB, LL_AHB2_GRP1_PERIPH_GPIOB},     // PB7 = USART1_RX (morpho header)
};

static bool initialized;
static uint32_t bus_hz;             // USART1's bus clock (PCLK2)
static uint32_t cur_baud;           // 0 = not configured yet
static bool tx_routed, rx_routed;

static struct su_raw acc;           // filled by the interrupt during a READ window
static volatile bool receiving;
static uint32_t window_end;         // timebase tick when the READ window ends

static void su_isr(const void *arg){

    ARG_UNUSED(arg);
    USART_TypeDef *u = SU_USART;
    uint32_t isr = u->ISR;

    if (isr & USART_ISR_ORE){
        u->ICR = USART_ICR_ORECF;
        if (receiving){
            acc.overruns++;
        }
    }
    if (isr & USART_ISR_RXNE){
        uint8_t b = (uint8_t)u->RDR;     // reading RDR clears RXNE
        if (isr & (USART_ISR_FE | USART_ISR_NE)){
            u->ICR = USART_ICR_FECF | USART_ICR_NCF;
        }
        if (receiving){
            if (acc.stored < SU_RX_MAX){
                acc.data[acc.stored++] = b;
            }
            acc.byte_count++;
            if (isr & USART_ISR_FE){
                acc.framing_errors++;
            }
        }
    }
}

// turn on the USART1 clock, read its rate and hook up its interrupt (once)
static int su_init(void){

    static const struct stm32_pclken clocks[] = STM32_DT_CLOCKS(SU_NODE);
    const struct device *clk = DEVICE_DT_GET(STM32_CLOCK_CONTROL_NODE);

    if (!device_is_ready(clk) || tb_init() != 0){
        return SU_HW;
    }
    if (clock_control_on(clk, (clock_control_subsys_t)&clocks[0]) != 0){
        return SU_HW;
    }
    if (clock_control_get_rate(clk, (clock_control_subsys_t)&clocks[0], &bus_hz) != 0 || bus_hz == 0){
        return SU_HW;
    }

    IRQ_CONNECT(SU_IRQ, DT_IRQ(SU_NODE, priority), su_isr, NULL, 0);
    irq_enable(SU_IRQ);
    initialized = true;
    return SU_OK;
}

static const struct su_pin *find(const struct su_pin *pins, size_t n, char port, uint8_t pin){

    for (size_t i = 0; i < n; i++){
        if (pins[i].port == port && pins[i].pin == pin){
            return &pins[i];
        }
    }
    return NULL;
}

// connect the pin to USART1 (alternate function 7)
static void route(const struct su_pin *p, uint32_t pull){

    uint32_t mask = 1u << p->pin;    // LL_GPIO_PIN_n == (1 << n)
    LL_AHB2_GRP1_EnableClock(p->gpio_clock);
    LL_GPIO_SetPinPull(p->gpio, mask, pull);
    LL_GPIO_SetPinOutputType(p->gpio, mask, LL_GPIO_OUTPUT_PUSHPULL);
    if (p->pin < 8){
        LL_GPIO_SetAFPin_0_7(p->gpio, mask, LL_GPIO_AF_7);
    }
    else {
        LL_GPIO_SetAFPin_8_15(p->gpio, mask, LL_GPIO_AF_7);
    }
    LL_GPIO_SetPinMode(p->gpio, mask, LL_GPIO_MODE_ALTERNATE);
}

// let the line sit idle for two characters, so a receiver that saw a glitch while the pin
// was being connected is back in sync before real data
static void idle_two_chars(uint32_t baud){
    k_usleep((int32_t)(20u * 1000000u / baud) + 1);
}

// 8N1 at baud (only reprogrammed when the baud changes)
static int set_baud(uint32_t baud){

    if (baud == 0){
        return SU_HW;
    }
    if (baud == cur_baud){
        return SU_OK;
    }

    USART_TypeDef *u = SU_USART;
    uint32_t src_hz = bus_hz;
    LL_USART_Disable(u);

    if (bus_hz / baud > 0xFFFFu){
        // too slow for the bus clock with a 16-bit divider: run the USART from HSI16
        LL_RCC_HSI_Enable();
        for (uint32_t i = 0; !LL_RCC_HSI_IsReady(); i++){
            if (i > 1000000u){
                return SU_HW;
            }
        }
        LL_RCC_SetUSARTClockSource(LL_RCC_USART1_CLKSOURCE_HSI);
        src_hz = HSI16_HZ;
    }
    else {
        LL_RCC_SetUSARTClockSource(LL_RCC_USART1_CLKSOURCE_PCLK2);
    }

    LL_USART_SetDataWidth(u, LL_USART_DATAWIDTH_8B);
    LL_USART_SetParity(u, LL_USART_PARITY_NONE);
    LL_USART_SetStopBitsLength(u, LL_USART_STOPBITS_1);
    LL_USART_SetOverSampling(u, LL_USART_OVERSAMPLING_16);
    u->BRR = (src_hz + baud / 2) / baud;      // oversampling 16: BRR = clock / baud
    LL_USART_SetTransferDirection(u, LL_USART_DIRECTION_TX_RX);
    LL_USART_Enable(u);

    cur_baud = baud;
    return SU_OK;
}

int su_send(char tx_port, uint8_t tx_pin, uint32_t baud, const uint8_t *data, size_t n){

    const struct su_pin *p = find(tx_pins, ARRAY_SIZE(tx_pins), tx_port, tx_pin);
    if (p == NULL){
        return SU_NO_USART;
    }
    if (!initialized && su_init() != SU_OK){
        return SU_HW;
    }
    if (receiving && baud != cur_baud){
        return SU_HW;     // a READ at another baud is running
    }
    if (set_baud(baud) != SU_OK){
        return SU_HW;
    }
    if (!tx_routed){
        route(p, LL_GPIO_PULL_NO);    // push-pull, idles high
        tx_routed = true;
        idle_two_chars(baud);
    }

    USART_TypeDef *u = SU_USART;
    for (size_t i = 0; i < n; i++){
        while (!LL_USART_IsActiveFlag_TXE(u)){
        }
        LL_USART_TransmitData8(u, data[i]);
    }
    while (!LL_USART_IsActiveFlag_TC(u)){      // last stop bit is out
    }
    return SU_OK;
}

int su_read_start(char rx_port, uint8_t rx_pin, uint32_t baud, uint32_t window_ms){

    const struct su_pin *p = find(rx_pins, ARRAY_SIZE(rx_pins), rx_port, rx_pin);
    if (p == NULL){
        return SU_NO_USART;
    }
    if (receiving){
        return SU_HW;
    }
    if (!initialized && su_init() != SU_OK){
        return SU_HW;
    }
    if (set_baud(baud) != SU_OK){
        return SU_HW;
    }
    if (!rx_routed){
        // pull-up: an undriven line (sketch not using Serial1, Nano in reset) reads as an
        // idle UART instead of noise bytes; it doesn't load the student's TX output
        route(p, LL_GPIO_PULL_UP);
        rx_routed = true;
        idle_two_chars(baud);
    }

    USART_TypeDef *u = SU_USART;
    LL_USART_DisableIT_RXNE(u);
    u->RQR = USART_RQR_RXFRQ;                  // drop anything received before the window
    u->ICR = USART_ICR_ORECF | USART_ICR_FECF | USART_ICR_NCF;

    acc.byte_count = 0;
    acc.stored = 0;
    acc.framing_errors = 0;
    acc.overruns = 0;
    window_end = tb_now() + tb_us_to_ticks(window_ms * 1000u);
    receiving = true;

    NVIC_ClearPendingIRQ(SU_IRQ);
    LL_USART_EnableIT_RXNE(u);
    return SU_OK;
}

int su_read_finish(struct su_raw *out){

    if (!receiving){
        return SU_HW;
    }
    tb_wait_until(window_end);

    LL_USART_DisableIT_RXNE(SU_USART);
    unsigned int key = irq_lock();
    receiving = false;
    irq_unlock(key);

    out->byte_count = acc.byte_count;
    out->stored = acc.stored;
    out->framing_errors = acc.framing_errors;
    out->overruns = acc.overruns;
    memcpy(out->data, acc.data, acc.stored);
    return SU_OK;
}

void su_read_cancel(void){

    if (receiving){
        LL_USART_DisableIT_RXNE(SU_USART);
        unsigned int key = irq_lock();
        receiving = false;
        irq_unlock(key);
    }
}