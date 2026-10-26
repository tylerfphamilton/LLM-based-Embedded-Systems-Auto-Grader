// This is the functionality for the UART layer
// The receive interrupt builds up a line one byte at a time. 
// When it sees \n it drops a trailing \r and pushes the finished line onto a message queue for the main thread
// Sending writes out one line and adds \name

#include "link.h"

#include <string.h>
#include <zephyr/device.h>
#include <zephyr/drivers/uart.h>
#include <zephyr/kernel.h>

// getting the UART (uart2) device
#define HOST_UART_NODE DT_CHOSEN(grader_host_uart)
static const struct device* const uart = DEVICE_DT_GET(HOST_UART_NODE);

// a queue for the data to be passed over the wire (one may be in transmission so need to store the ones that are ready)
K_MSGQ_DEFINE(line_q, sizeof(struct line), 4, 4);

// for constructing the message
static struct line rx;
static size_t rx_len;

// function for putting the line on the queue if we are unable to send at this moment
static void finish_line(void){

    // check the carraige return
    if (!rx.too_long && rx_len > 0 && rx.text[rx_len - 1] == '\r'){
        rx_len--;
    }

    // add null terminating char
    rx.text[rx_len] = '\0';

    // put on the wait queue
    (void) k_msgq_put(&line_q, &rx, K_NO_WAIT);

    // reset the variables
    rx_len = 0;
    rx.too_long = false;
}

// Todo: Need to come up with comments for this function and the lines in it 
static void uart_isr(const struct device* dev, void* user_data){

    // byte to store the data into from the fifo
    uint8_t c;

    // to silence the unused parameter warning - no data coming in yet
    ARG_UNUSED(user_data);

    // if the dev doesn't need to be updated or is not ready, return
    if(!uart_irq_update(dev) || !uart_irq_rx_ready(dev)){
        return;
    }

    // while there is still data in the fifo () -> telling the driver which UART to read from
    while(uart_fifo_read(dev, &c, 1) == 1){
        
        // if the char from the fifo is the new line character, call the finish line function so we can send it out
        if (c == '\n'){
            finish_line();
        }
        // if the received length is less than the max sending length, add the char from the fifo to the struct
        else if (rx_len < LINE_MAX){
            rx.text[rx_len++] = (char) c;
        }
        else {
            rx.too_long = true;
        }
    }
}

// function for initializing uart (the link)
int link_init(void){
    
    // local variable declarations (junk is for useless data and ret is for checking the return type of the callback isr function)
    uint8_t junk;
    int ret;

    // if there is a tranmsission still active
    if (!device_is_ready(uart)){
        return -ENODEV;
    }

    // Drop anything that arrived before we were ready
    while (uart_poll_in(uart, &junk) == 0){}

    // the uart link is ready now, call the isr callback function and check the return type
    ret = uart_irq_callback_user_data_set(uart, uart_isr, NULL);
    if (ret < 0){
        return ret;
    }
    
    // enable rx interrupts
    uart_irq_rx_enable(uart);
    return 0;
}


void link_get_line(struct line *out){
    
    // k_msgq_get takes the oldest message out of line_q and copies it into the *out variable
    // K_FOREVER means: if the queue is empty, put this thread to sleep until something arrives
    (void) k_msgq_get(&line_q, out, K_FOREVER);
}


void link_send_line(const char* text){

    // iterate one char at a time until the null terminator and then append the \n
    for (const char* p = text; *p != '\0'; p++){
        // busy waits the USART data register (blocking)
        uart_poll_out(uart, (unsigned char)*p);
    }
    uart_poll_out(uart, '\n');
}

