/*
 * PC test harness for the plain-C firmware parts: reply.c, cmd.c and the generated
 * pins_gen.h. Built and run by tests/firmware/test_reply_c.py, which compares every line
 * with what grader.protocol produces for the same values.
 *
 * Output: one "<case>\t<reply line>" per case.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "cmd.h"
#include "pins_gen.h"
#include "reply.h"

/* pins.c is Zephyr code; this is the one definition the harness needs from it. */
const char pins_map_hash[] = PINMAP_HASH;

static const char *current;

static void out(const char *line) {
    printf("%s\t%s\n", current, line);
}

#define STR(r, key, s) reply_str((r), (key), (const uint8_t *)(s), sizeof(s) - 1)

int main(void) {
    struct reply_buf r;

    current = "ints";
    reply_begin(&r);
    reply_int(&r, "a", 0);
    reply_int(&r, "b", 1000);
    reply_int(&r, "c", -42);
    reply_int(&r, "d", INT64_MAX);
    reply_int(&r, "e", INT64_MIN);
    reply_send(&r, out);

    current = "fixed";
    reply_begin(&r);
    reply_fixed(&r, "f", 999873, 3);
    reply_fixed(&r, "zero", 0, 3);
    reply_fixed(&r, "neg", -1500, 3);
    reply_fixed(&r, "negsmall", -5, 3);
    reply_fixed(&r, "whole", 1000000, 3);
    reply_fixed(&r, "nodec", 7, 0);
    reply_fixed(&r, "pct", 4998, 2);
    reply_send(&r, out);

    current = "null";
    reply_begin(&r);
    reply_null(&r, "frequency_hz");
    reply_int(&r, "edge_count", 1);
    reply_send(&r, out);

    current = "strings";
    reply_begin(&r);
    STR(&r, "empty", "");
    STR(&r, "plain", "ON");
    STR(&r, "space", "hello world");
    STR(&r, "punct", "a,b\"c%d");
    STR(&r, "ctrl", "ON\r\n\t\x01\x7f");
    STR(&r, "nul", "a\0b");
    STR(&r, "utf8", "caf\xc3\xa9 \xc2\xb5s");
    STR(&r, "high", "\xff\x80");
    reply_send(&r, out);

    current = "empty_list";
    reply_begin(&r);
    reply_list_fixed(&r, "edges_ms", NULL, 0, 3);
    reply_send(&r, out);

    current = "list";
    {
        static const int64_t v[] = {500, 250500, -1, 0, 1000};
        reply_begin(&r);
        reply_int(&r, "edge_count", 5);
        reply_list_fixed(&r, "edges_ms", v, 5, 3);
        reply_int(&r, "final_level", 1);
        reply_send(&r, out);
    }

    current = "truncated_list";
    {
        static int64_t v[400];
        for (int i = 0; i < 400; i++) {
            v[i] = 123456 + 1000 * (int64_t)i;
        }
        reply_begin(&r);
        reply_int(&r, "edge_count", 400);
        reply_list_fixed(&r, "edges_ms", v, 400, 3);
        reply_send(&r, out);
    }

    current = "overflow";
    {
        uint8_t junk[300];
        memset(junk, 0x01, sizeof(junk)); /* 3 chars each once escaped */
        reply_begin(&r);
        reply_str(&r, "a", junk, sizeof(junk));
        reply_str(&r, "b", junk, sizeof(junk));
        reply_send(&r, out);
    }

    current = "err";
    reply_err(out, "BADPIN", "pin D7 is not in the pin map");
    current = "err_nomsg";
    reply_err(out, "TIMEOUT", "");

    /* the real command handler */
    {
        char line[64];

        current = "ping";
        strcpy(line, "PING");
        cmd_handle(line, out);

        current = "ping_args";
        strcpy(line, "PING now");
        cmd_handle(line, out);

        current = "unknown";
        strcpy(line, "JUMP D5");
        cmd_handle(line, out);

        current = "blank";
        strcpy(line, "   ");
        cmd_handle(line, out);
    }

    /* the generated pin table */
    current = "pins";
    for (size_t i = 0; i < PINS_COUNT; i++) {
        printf("pin\t%s %c %u %lu\n", PINS[i].name, PINS[i].port ? PINS[i].port : '-',
               (unsigned)PINS[i].pin, (unsigned long)PINS[i].caps);
    }
    return 0;
}
