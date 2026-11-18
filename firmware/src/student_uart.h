// UART: talk to the student's Serial1 through the STM32's USART1 (8 data bits, no parity,
// 1 stop bit). Plain C header (no Zephyr includes) so cmd.c can still be compiled and
// tested on a PC; the implementation in student_uart.c is Zephyr + STM32 LL code.
#ifndef GRADER_STUDENT_UART_H
#define GRADER_STUDENT_UART_H

#include <stddef.h>
#include <stdint.h>

// bytes stored per READ window. A reply line only has room for ~950 printable bytes
// anyway; bytes beyond this are still counted in byte_count.
#define SU_RX_MAX 1024

// raw result of one READ window
struct su_raw {
    uint32_t byte_count;        // every byte received in the window
    uint32_t stored;            // how many of them are in data[] (at most SU_RX_MAX)
    uint32_t framing_errors;    // bytes with a framing error (wrong baud, noise); still stored
    uint32_t overruns;          // bytes lost because the board read too slowly (a rig fault)
    uint8_t data[SU_RX_MAX];    // the bytes, in order, exactly as received
};

// su_* return codes
enum {
    SU_OK = 0,
    SU_NO_USART = -1,   // the pin can't be routed to USART1
    SU_HW = -2,         // clock, timebase or USART setup failed
};

// Send n bytes on STM32 pin P<tx_port><tx_pin> at baud. Blocks until the last stop bit
// is out. The pin stays a UART output afterwards (idle high, like a real UART).
int su_send(char tx_port, uint8_t tx_pin, uint32_t baud, const uint8_t *data, size_t n);

// Start receiving on STM32 pin P<rx_port><rx_pin> at baud for window_ms; returns at once.
// (ARM/COLLECT will call start and finish separately.)
int su_read_start(char rx_port, uint8_t rx_pin, uint32_t baud, uint32_t window_ms);

// Block until the window ends, stop receiving and fill *out.
int su_read_finish(struct su_raw *out);

// su_read_start + su_read_finish: the blocking UART READ command.
int su_read(char rx_port, uint8_t rx_pin, uint32_t baud, uint32_t window_ms, struct su_raw *out);

#endif