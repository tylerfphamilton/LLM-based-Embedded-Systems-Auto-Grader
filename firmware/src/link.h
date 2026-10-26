// header for the UART layer (named link.h)
#ifndef GRADER_LINK_H
#define GRADER_LINK_H

// included header files
#include <stdbool.h>
#include <stddef.h>

// max length of a transmission over UART (from docs/protocol.md - excluding the null terminator)
#define LINE_MAX 1024

// info for transmitting data
struct line {
    char text[LINE_MAX + 1];    // added one for the null terminator
    bool too_long;  // boolean to see if the line length was longer than LINE_MAX because the text is cutoff in this case
};


// Sets up the host UART and its receive interrupt - returns 0 if successfull and negative errno if failed
int link_init(void);

// function that blocks until the next complete line from the host arrives
void link_get_line(struct line *out);

// functions that sends one line to the host (\n is appended)
void link_send_line(const char *text);

#endif