// builds "OK key=value ..." reply lines in the format of docs/protocol.md ("Value encoding")
// Plain C (no Zephyr includes) so it can be compiled and tested on a PC: tests/firmware/test_reply_c.py
#ifndef GRADER_REPLY_H
#define GRADER_REPLY_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "cmd.h"    // reply_fn
#include "link.h"   // PROTO_LINE_MAX

// a reply being built. Once anything doesn't fit, overflow is set and reply_send sends an ERR instead
struct reply_buf {
    char text[PROTO_LINE_MAX + 1];    // added one for the null terminator
    size_t len;
    bool overflow;
    bool truncated;             // a list was cut short and " truncated=1" was already added
};

// starts the line with "OK"
void reply_begin(struct reply_buf *r);

// " key=-12"
void reply_int(struct reply_buf *r, const char *key, int64_t v);

// " key=999.873" from scaled=999873, decimals=3. Never uses floats. Trailing zeros are dropped
// but at least one decimal is kept ("1000.0"), which is how the host prints the same float
void reply_fixed(struct reply_buf *r, const char *key, int64_t scaled, int decimals);

// " key=null"
void reply_null(struct reply_buf *r, const char *key);

// " key="..."" quoted; bytes outside 0x21-0x7E and % " , become %XX
void reply_str(struct reply_buf *r, const char *key, const uint8_t *bytes, size_t n);

// " key=[a,b,c]" of fixed-point values. If the whole list doesn't fit in the line, it stops
// before the limit and adds " truncated=1" after the list
void reply_list_fixed(struct reply_buf *r, const char *key, const int64_t *scaled, size_t n, int decimals);

// sends the line, or "ERR INTERNAL reply too long" if it overflowed
void reply_send(struct reply_buf *r, reply_fn reply);

// sends "ERR <CODE> <msg>" (just "ERR <CODE>" if msg is empty); msg is cut to fit the line
void reply_err(reply_fn reply, const char *code, const char *msg);

#endif
