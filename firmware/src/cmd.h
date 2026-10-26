#ifndef GRADER_CMD_H
#define GRADER_CMD_H

#include <stddef.h>

// called with each reply line (no terminator)
typedef void (*reply_fn)(const char* line);

// Handles one request line from the host and send exactly one reply through 'reply'
void cmd_handle(char* line, reply_fn reply);

#endif
