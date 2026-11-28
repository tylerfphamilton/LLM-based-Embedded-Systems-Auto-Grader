// DAC: the STM32 outputs an analog voltage into the student's analog input (a simulated
// potentiometer or analog sensor). Plain C header (no Zephyr includes) so cmd.c can still
// be compiled and tested on a PC; the implementation in dac_out.c is Zephyr + STM32 LL code.
#ifndef GRADER_DAC_OUT_H
#define GRADER_DAC_OUT_H

#include <stdint.h>

// highest voltage the DAC can be asked for: its full scale is VDDA (3.3 V on the Nucleo)
#define DAC_OUT_MAX_MV 3300u

// dac_out_set return codes
enum {
    DAC_OUT_OK = 0,
    DAC_OUT_NO_CHANNEL = -1,    // this STM32 pin is not a DAC output
    DAC_OUT_HW = -2,            // the DAC clock could not be turned on
};

// Output mv (0-DAC_OUT_MAX_MV) on STM32 pin P<port><pin> and keep it there until the
// next call. Returns once the output has settled.
int dac_out_set(char port, uint8_t pin, uint32_t mv);

#endif