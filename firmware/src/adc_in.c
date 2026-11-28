// ADC implementation: see adc_in.h.
//
// ADC1 is driven directly with STM32 LL (the overlay disables Zephyr's ADC driver for it).
// TIM6 (a basic timer with no pins) runs at 50 kHz and its update event triggers each
// conversion in hardware, and DMA1 channel 1 copies each result into a buffer. No
// interrupt is involved per sample, so nothing the CPU does (the host link's interrupt
// copying a 1 KB request line, other measurements) can delay a sample or lose one; the
// sum, min and max are worked out from the buffer at the end, in the calling thread.
//
// Millivolts: before each run the ADC measures its internal reference (VREFINT), whose
// factory calibration value gives the real VDDA, so a count converts to mV without
// assuming the Nucleo's supply is exactly 3.3 V.
//
// ADC clock: synchronous HCLK / 4 = 20 MHz (the board file's setting for Zephyr's own
// driver). Input channels sample for 47.5 cycles (~2.4 us, plenty for a push-pull output
// or the DAC behind 1 kOhm), so a conversion takes 3 us of each 20 us; VREFINT samples
// for 247.5 cycles (~12 us, its datasheet minimum is 4 us).

#include "adc_in.h"

#include <stdbool.h>
#include <zephyr/device.h>
#include <zephyr/devicetree.h>
#include <zephyr/drivers/clock_control.h>
#include <zephyr/drivers/clock_control/stm32_clock_control.h>
#include <zephyr/kernel.h>

#include <stm32_ll_adc.h>
#include <stm32_ll_bus.h>
#include <stm32_ll_dma.h>
#include <stm32_ll_gpio.h>
#include <stm32_ll_tim.h>

#include "timebase.h"

#define ADC_NODE    DT_NODELABEL(adc1)
#define DMA_CH      LL_DMA_CHANNEL_1    // DMA1 channel 1, request 0 = ADC1 (STM32L476 RM)
#define TRIG_NODE   DT_NODELABEL(timers6)
#define TRIG_TIM    ((TIM_TypeDef *)DT_REG_ADDR(TRIG_NODE))
#define VREF_READS  8           // VREFINT conversions averaged per run

// STM32 pins with an ADC input on the Nucleo's headers (STM32L476 datasheet, ADC12_INx)
struct adc_pin {
    char port;
    uint8_t pin;
    GPIO_TypeDef *gpio;
    uint32_t gpio_clock;
    uint32_t channel;
};

static const struct adc_pin adc_pins[] = {
    {'A', 0, GPIOA, LL_AHB2_GRP1_PERIPH_GPIOA, LL_ADC_CHANNEL_5},   // PA0 = ADC12_IN5 (header A0)
    {'A', 4, GPIOA, LL_AHB2_GRP1_PERIPH_GPIOA, LL_ADC_CHANNEL_9},   // PA4 = ADC12_IN9 (header A2)
    {'B', 0, GPIOB, LL_AHB2_GRP1_PERIPH_GPIOB, LL_ADC_CHANNEL_15},  // PB0 = ADC12_IN15 (header A3)
};

static bool initialized;
static const struct adc_pin *active;    // the pin of the running measurement, or NULL
static uint32_t target;                 // samples to take
static uint32_t vdda_mv;
static uint32_t run_end;                // timebase tick when the last sample is due
static uint16_t samples_buf[ADC_IN_MAX_SAMPLES];    // filled by DMA (20 KB)

static void stop_trigger(void){
    LL_TIM_DisableCounter(TRIG_TIM);
}

// bounded busy-wait for a hardware flag: true once cond holds, false if it never does
#define WAIT_UNTIL(cond) ({                         \
        bool ok_ = false;                           \
        for (uint32_t i_ = 0; i_ < 100000u; i_++){  \
            if (cond){                              \
                ok_ = true;                         \
                break;                              \
            }                                       \
        }                                           \
        ok_;                                        \
    })

// power up, calibrate and enable ADC1, set up TIM6 as its trigger and DMA1 to collect (once)
static int adc_init(void){

    static const struct stm32_pclken adc_clocks[] = STM32_DT_CLOCKS(ADC_NODE);
    static const struct stm32_pclken tim_clocks[] = STM32_DT_CLOCKS(TRIG_NODE);
    const struct device *clk = DEVICE_DT_GET(STM32_CLOCK_CONTROL_NODE);
    uint32_t tim_hz;

    if (!device_is_ready(clk)){
        return ADC_IN_HW;
    }
    // clocks[0] = bus clock gate; TIM6 clocks[1] = its kernel clock (TIMPCLK1, 80 MHz)
    if (clock_control_on(clk, (clock_control_subsys_t)&adc_clocks[0]) != 0 ||
        clock_control_on(clk, (clock_control_subsys_t)&tim_clocks[0]) != 0 ||
        clock_control_get_rate(clk, (clock_control_subsys_t)&tim_clocks[1], &tim_hz) != 0){
        return ADC_IN_HW;
    }

    ADC_Common_TypeDef *common = __LL_ADC_COMMON_INSTANCE(ADC1);
    LL_ADC_SetCommonClock(common, LL_ADC_CLOCK_SYNC_PCLK_DIV4);
    LL_ADC_SetCommonPathInternalCh(common, LL_ADC_PATH_INTERNAL_VREFINT);

    LL_ADC_DisableDeepPowerDown(ADC1);
    LL_ADC_EnableInternalRegulator(ADC1);
    k_busy_wait(LL_ADC_DELAY_INTERNAL_REGUL_STAB_US);

    LL_ADC_StartCalibration(ADC1, LL_ADC_SINGLE_ENDED);
    if (!WAIT_UNTIL(!LL_ADC_IsCalibrationOnGoing(ADC1))){
        return ADC_IN_HW;
    }
    k_busy_wait(1);     // >= 4 ADC clocks between calibration and enable

    LL_ADC_SetResolution(ADC1, LL_ADC_RESOLUTION_12B);
    LL_ADC_SetDataAlignment(ADC1, LL_ADC_DATA_ALIGN_RIGHT);
    LL_ADC_REG_SetSequencerLength(ADC1, LL_ADC_REG_SEQ_SCAN_DISABLE);
    LL_ADC_REG_SetContinuousMode(ADC1, LL_ADC_REG_CONV_SINGLE);
    LL_ADC_REG_SetOverrun(ADC1, LL_ADC_REG_OVR_DATA_PRESERVED);
    LL_ADC_SetChannelSamplingTime(ADC1, LL_ADC_CHANNEL_VREFINT, LL_ADC_SAMPLINGTIME_247CYCLES_5);

    LL_ADC_ClearFlag_ADRDY(ADC1);
    LL_ADC_Enable(ADC1);
    if (!WAIT_UNTIL(LL_ADC_IsActiveFlag_ADRDY(ADC1))){
        return ADC_IN_HW;
    }
    k_busy_wait(LL_ADC_DELAY_VREFINT_STAB_US);

    // TIM6: free-running at the full timer clock, an update (and TRGO) every 20 us
    LL_TIM_DisableCounter(TRIG_TIM);
    LL_TIM_SetPrescaler(TRIG_TIM, 0);
    LL_TIM_SetAutoReload(TRIG_TIM, tim_hz / (1000000u / ADC_IN_SAMPLE_US) - 1);
    LL_TIM_SetTriggerOutput(TRIG_TIM, LL_TIM_TRGO_UPDATE);
    LL_TIM_GenerateEvent_UPDATE(TRIG_TIM);

    // DMA1 channel 1: ADC1's data register -> samples_buf, one halfword per conversion
    LL_AHB1_GRP1_EnableClock(LL_AHB1_GRP1_PERIPH_DMA1);
    LL_DMA_DisableChannel(DMA1, DMA_CH);
    LL_DMA_SetPeriphRequest(DMA1, DMA_CH, LL_DMA_REQUEST_0);
    LL_DMA_ConfigTransfer(DMA1, DMA_CH,
                          LL_DMA_DIRECTION_PERIPH_TO_MEMORY | LL_DMA_MODE_NORMAL |
                          LL_DMA_PERIPH_NOINCREMENT | LL_DMA_MEMORY_INCREMENT |
                          LL_DMA_PDATAALIGN_HALFWORD | LL_DMA_MDATAALIGN_HALFWORD |
                          LL_DMA_PRIORITY_HIGH);
    LL_DMA_ConfigAddresses(DMA1, DMA_CH,
                           LL_ADC_DMA_GetRegAddr(ADC1, LL_ADC_DMA_REG_REGULAR_DATA),
                           (uint32_t)samples_buf, LL_DMA_DIRECTION_PERIPH_TO_MEMORY);

    if (tb_init() != 0){
        return ADC_IN_HW;
    }
    initialized = true;
    return ADC_IN_OK;
}

// VDDA in mV from VREFINT (software-triggered conversions, interrupt off); 0 on failure
static uint32_t measure_vdda(void){

    uint32_t sum = 0;
    LL_ADC_REG_SetTriggerSource(ADC1, LL_ADC_REG_TRIG_SOFTWARE);
    LL_ADC_REG_SetSequencerRanks(ADC1, LL_ADC_REG_RANK_1, LL_ADC_CHANNEL_VREFINT);
    for (int i = 0; i < VREF_READS; i++){
        LL_ADC_ClearFlag_EOC(ADC1);
        LL_ADC_REG_StartConversion(ADC1);
        if (!WAIT_UNTIL(LL_ADC_IsActiveFlag_EOC(ADC1))){
            return 0;
        }
        sum += LL_ADC_REG_ReadConversionData12(ADC1);
    }
    uint32_t raw = (sum + VREF_READS / 2) / VREF_READS;
    return raw == 0 ? 0 : __LL_ADC_CALC_VREFANALOG_VOLTAGE(raw, LL_ADC_RESOLUTION_12B);
}

static void stop(void){

    stop_trigger();
    if (LL_ADC_REG_IsConversionOngoing(ADC1)){
        LL_ADC_REG_StopConversion(ADC1);
        (void)WAIT_UNTIL(!LL_ADC_REG_IsStopConversionOngoing(ADC1));
    }
    LL_ADC_REG_SetDMATransfer(ADC1, LL_ADC_REG_DMA_TRANSFER_NONE);
    LL_DMA_DisableChannel(DMA1, DMA_CH);
    // disconnect the ADC's analog switch; the pin stays analog (other commands set the mode
    // they need, and the DAC pin must stay analog anyway)
    LL_GPIO_DisablePinAnalogControl(active->gpio, 1u << active->pin);
    active = NULL;
}

int adc_in_start(char port, uint8_t pin, uint32_t samples){

    const struct adc_pin *p = NULL;
    for (size_t i = 0; i < ARRAY_SIZE(adc_pins); i++){
        if (adc_pins[i].port == port && adc_pins[i].pin == pin){
            p = &adc_pins[i];
        }
    }
    if (p == NULL){
        return ADC_IN_NO_CHANNEL;
    }
    if (active != NULL || samples == 0 || samples > ADC_IN_MAX_SAMPLES){
        return ADC_IN_HW;       // one at a time (cmd.c reports BUSY / BADARG before this)
    }
    if (!initialized && adc_init() != ADC_IN_OK){
        return ADC_IN_HW;
    }

    vdda_mv = measure_vdda();
    if (vdda_mv == 0){
        return ADC_IN_HW;
    }

    // the pin: analog mode, with the analog switch to the ADC closed (ASCR, STM32L47x)
    uint32_t mask = 1u << p->pin;
    LL_AHB2_GRP1_EnableClock(p->gpio_clock);
    LL_GPIO_SetPinMode(p->gpio, mask, LL_GPIO_MODE_ANALOG);
    LL_GPIO_EnablePinAnalogControl(p->gpio, mask);

    LL_ADC_SetChannelSamplingTime(ADC1, p->channel, LL_ADC_SAMPLINGTIME_47CYCLES_5);
    LL_ADC_REG_SetSequencerRanks(ADC1, LL_ADC_REG_RANK_1, p->channel);
    LL_ADC_REG_SetTriggerSource(ADC1, LL_ADC_REG_TRIG_EXT_TIM6_TRGO);
    LL_ADC_REG_SetTriggerEdge(ADC1, LL_ADC_REG_TRIG_EXT_RISING);

    target = samples;
    active = p;

    // DMA: `samples` transfers into the buffer, then it stops (the ADC's DMA requests with it)
    LL_DMA_DisableChannel(DMA1, DMA_CH);
    LL_DMA_SetDataLength(DMA1, DMA_CH, samples);
    LL_DMA_ClearFlag_GI1(DMA1);
    LL_DMA_EnableChannel(DMA1, DMA_CH);
    LL_ADC_REG_SetDMATransfer(ADC1, LL_ADC_REG_DMA_TRANSFER_LIMITED);
    LL_ADC_ClearFlag_EOC(ADC1);
    LL_ADC_ClearFlag_OVR(ADC1);

    LL_ADC_REG_StartConversion(ADC1);       // armed: each TIM6 update starts one conversion
    LL_TIM_SetCounter(TRIG_TIM, 0);
    run_end = tb_now() + tb_us_to_ticks(samples * ADC_IN_SAMPLE_US);
    LL_TIM_EnableCounter(TRIG_TIM);
    return ADC_IN_OK;
}

int adc_in_finish(struct adc_in_raw *out){

    if (active == NULL){
        return ADC_IN_HW;
    }
    // the run takes samples * 20 us; then give the DMA up to 20 ms more to report done
    tb_wait_until(run_end);
    for (int i = 0; i < 200 && LL_DMA_GetDataLength(DMA1, DMA_CH) != 0; i++){
        k_usleep(100);
    }
    uint32_t left = LL_DMA_GetDataLength(DMA1, DMA_CH);
    stop();

    // sum, min and max of what the DMA stored
    uint32_t n = target - left, sum = 0;
    uint16_t lo = UINT16_MAX, hi = 0;
    for (uint32_t i = 0; i < n; i++){
        uint16_t v = samples_buf[i];
        sum += v;
        lo = v < lo ? v : lo;
        hi = v > hi ? v : hi;
    }
    out->count = n;
    out->sum = sum;
    out->min = lo;
    out->max = hi;
    out->overruns = 0;      // DMA reads every result within a bus cycle: none are lost
    out->vdda_mv = vdda_mv;
    return left == 0 ? ADC_IN_OK : ADC_IN_HW;
}

void adc_in_cancel(void){

    if (active != NULL){
        stop();
    }
}

uint32_t adc_in_vdda_mv(void){

    if (active != NULL){
        return vdda_mv;
    }
    if (!initialized && adc_init() != ADC_IN_OK){
        return 0;
    }
    vdda_mv = measure_vdda();
    return vdda_mv;
}