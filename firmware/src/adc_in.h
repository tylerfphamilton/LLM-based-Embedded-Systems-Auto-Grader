// ADC: the STM32 samples a voltage on one of the student's pins (an analog level, or the
// average of a PWM output). Plain C header (no Zephyr includes) so cmd.c can still be
// compiled and tested on a PC; the implementation in adc_in.c is Zephyr + STM32 LL code.
#ifndef GRADER_ADC_IN_H
#define GRADER_ADC_IN_H

#include <stdint.h>

// one sample every ADC_IN_SAMPLE_US (50 kHz), the rate the host assumes for its timeouts
// (grader.protocol.Adc: 0.02 ms per sample). A window of n samples lasts n * 20 us, so a
// PWM output is averaged over many periods (1000 samples = 20 ms = 20 periods at 1 kHz).
#define ADC_IN_SAMPLE_US 20u

// most samples per measurement (validate.py allows 1-10000)
#define ADC_IN_MAX_SAMPLES 10000u


// raw result of one measurement, in 12-bit ADC counts (0-4095 = 0-VDDA)
struct adc_in_raw {
    uint32_t count;     // samples taken
    uint32_t sum;       // sum of all samples (at most 10000 * 4095, fits 32 bits)
    uint16_t min;       // lowest sample
    uint16_t max;       // highest sample
    uint32_t vdda_mv;   // the ADC's full scale (VDDA), measured from VREFINT before the run
    uint32_t overruns;  // samples lost (rig fault); the DMA never loses any, so always 0 now
};

// adc_in_* return codes
enum {
    ADC_IN_OK = 0,
    ADC_IN_NO_CHANNEL = -1,     // this STM32 pin is not an ADC input
    ADC_IN_HW = -2,             // clock, calibration, VREFINT or sampling failed
};

// Start taking `samples` samples (1-ADC_IN_MAX_SAMPLES) on STM32 pin P<port><pin>;
// returns at once. One measurement at a time.
int adc_in_start(char port, uint8_t pin, uint32_t samples);

// Block until every sample is taken, stop and fill *out.
int adc_in_finish(struct adc_in_raw *out);

// Stop a running measurement without a result (RESET). Does nothing if none is running.
void adc_in_cancel(void);

// The Nucleo's analog supply (VDDA, the DAC's and ADC's full scale) in mV, measured from
// VREFINT. While a measurement runs it returns the value measured at that run's start
// (the ADC is busy). 0 if the ADC could not be started.
uint32_t adc_in_vdda_mv(void);

#endif