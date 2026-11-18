/*
 * PC test harness for the plain-C firmware parts: reply.c, cmd.c, pins_table.c and the
 * generated pins_gen.h. Built and run by tests/firmware/test_reply_c.py, which compares
 * every line with what grader.protocol produces for the same values.
 *
 * Output: one "<case>\t<reply line>" per case, "pin\t..." per pin-table row and
 * "freqpin\t<name>\t<reply line>" for FREQ on every pin in the table.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "capture.h"
#include "cmd.h"
#include "pins_gen.h"
#include "reply.h"
#include "rig.h"
#include "trace.h"


/* trace.c is Zephyr + GPIO interrupts; this stand-in returns canned edge lists. */
static struct trace_raw stub_trace;
static int stub_trace_rc;
static char stub_trace_port;
static unsigned stub_trace_pin, stub_trace_window;

int trace_measure(char port, uint8_t pin, uint32_t window_ms, struct trace_raw *out) {
    stub_trace_port = port;
    stub_trace_pin = pin;
    stub_trace_window = window_ms;
    *out = stub_trace;
    return stub_trace_rc;
}

/* n edges, the first `first_us` after the window start, then every `step_us`; only the
   first `keep` are stored (as when the firmware's buffer fills up) */
static void stub_edges(uint32_t n, uint32_t keep, uint32_t first_us, uint32_t step_us,
                       uint8_t final_level) {
    const uint32_t hz = 80000000u;
    stub_trace_rc = TRACE_OK;
    stub_trace.clock_hz = hz;
    stub_trace.start = 4290000000u; /* just before the 32-bit wrap: spans must not care */
    stub_trace.edge_count = n;
    stub_trace.stored = keep < n ? keep : n;
    for (uint32_t i = 0; i < stub_trace.stored; i++) {
        uint64_t us = (uint64_t)first_us + (uint64_t)i * step_us;
        stub_trace.t[i] = stub_trace.start + (uint32_t)(us * (hz / 1000000u));
    }
    stub_trace.final_level = final_level;
}

/* rig.c is Zephyr + GPIO; these stand-ins record what the firmware asked for. */
static long stub_slept_ms = -1;
static int stub_reset_rc;
static int stub_resets;
static char stub_reset_port;
static unsigned stub_reset_pin;

void rig_sleep_ms(uint32_t ms) {
    stub_slept_ms = (long)ms;
}

int rig_reset_pulse(char port, uint8_t pin) {
    stub_resets++;
    stub_reset_port = port;
    stub_reset_pin = pin;
    return stub_reset_rc;
}

/* capture.c is Zephyr + timer hardware; this stand-in returns canned captures. */
static struct capture_raw stub_raw;
static int stub_rc;
static char stub_port;
static unsigned stub_pin, stub_window;

int capture_measure(char port, uint8_t pin, uint32_t window_ms, struct capture_raw *out) {
    stub_port = port;
    stub_pin = pin;
    stub_window = window_ms;
    *out = stub_raw;
    return stub_rc;
}

/* a periodic signal: n rising edges, `period` ticks apart, high for `high` ticks */
static void stub_signal(uint32_t clock_hz, uint32_t n, uint32_t period, uint32_t high) {
    stub_rc = CAPTURE_OK;
    stub_raw = (struct capture_raw){0};
    stub_raw.clock_hz = clock_hz;
    stub_raw.rising = n;
    stub_raw.falling = n;
    stub_raw.first_rise = 4000000000u; /* close to the 32-bit wrap: spans must not care */
    stub_raw.last_rise = stub_raw.first_rise + (n ? n - 1 : 0) * period;
    stub_raw.high_ticks = (uint64_t)n * high;
    stub_raw.high_count = n;
}

static const char *current;

static void out(const char *line) {
    printf("%s\t%s\n", current, line);
}

static void freq(const char *name, const char *request) {
    char line[64];
    current = name;
    strcpy(line, request);
    cmd_handle(line, out);
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

    /* FREQ on every pin of the table, with a 1 kHz 25% signal behind the stub */
    for (size_t i = 0; i < PINS_COUNT; i++) {
        char line[64], tag[80];
        stub_signal(80000000u, 100, 80000, 20000);
        snprintf(line, sizeof(line), "FREQ %s 100", PINS[i].name);
        snprintf(tag, sizeof(tag), "freqpin\t%s", PINS[i].name);
        current = tag;
        cmd_handle(line, out);
    }

    /* FREQ arithmetic and errors, on the first wired capture pin (if the map has one) */
    for (size_t i = 0; i < PINS_COUNT; i++) {
        char req[64];
        if (PINS[i].port == 0 || !(PINS[i].caps & CAP_TIMER_CAPTURE)) {
            continue;
        }
        current = "freq_pin";
        out(PINS[i].name);

        stub_signal(80000000u, 100, 80000, 20000); /* 1000 Hz, 25 % */
        snprintf(req, sizeof(req), "FREQ %s 100", PINS[i].name);
        freq("freq_1k", req);
        printf("freq_call\t%c %u %u\n", stub_port, stub_pin, stub_window);

        stub_signal(80000000u, 50, 160000, 40160); /* 500 Hz, 25.1 % */
        freq("freq_500", req);

        stub_signal(80000000u, 102, 78447, 19612); /* ~1019.797 Hz */
        freq("freq_odd", req);

        stub_signal(80000000u, 0, 0, 0); /* no signal */
        freq("freq_nosig", req);

        stub_signal(80000000u, 1, 0, 0); /* one rising edge only */
        freq("freq_one", req);

        stub_signal(80000000u, 100, 80000, 20000);
        stub_raw.overruns = 3;
        freq("freq_overrun", req);

        stub_signal(80000000u, 100, 80000, 20000);
        stub_rc = CAPTURE_NO_TIMER;
        freq("freq_notimer", req);

        stub_rc = CAPTURE_HW;
        freq("freq_hw", req);

        stub_signal(80000000u, 100, 80000, 20000);
        snprintf(req, sizeof(req), "FREQ %s 0", PINS[i].name);
        freq("freq_win0", req);
        snprintf(req, sizeof(req), "FREQ %s 10001", PINS[i].name);
        freq("freq_winbig", req);
        snprintf(req, sizeof(req), "FREQ %s 1e3", PINS[i].name);
        freq("freq_winsyntax", req);
        snprintf(req, sizeof(req), "FREQ %s 10000", PINS[i].name);
        freq("freq_winmax", req);
        snprintf(req, sizeof(req), "FREQ %s", PINS[i].name);
        freq("freq_args", req);
        break;
    }
    freq("freq_unknown", "FREQ D99 100");

    /* WAIT: each case prints the reply, then how long the stub was asked to sleep (-1 = never) */
    {
        static const char *const waits[][2] = {
            {"wait_500", "WAIT 500"},     {"wait_0", "WAIT 0"},
            {"wait_max", "WAIT 60000"},   {"wait_big", "WAIT 60001"},
            {"wait_neg", "WAIT -5"},      {"wait_frac", "WAIT 1.5"},
            {"wait_args", "WAIT"},        {"wait_extra", "WAIT 5 6"},
        };
        for (size_t i = 0; i < sizeof(waits) / sizeof(waits[0]); i++) {
            stub_slept_ms = -1;
            freq(waits[i][0], waits[i][1]);
            printf("%s_slept\t%ld\n", waits[i][0], stub_slept_ms);
        }
    }

    /* RESET: prints the reply, then how many pulses and on which STM32 pin */
    stub_resets = 0;
    stub_reset_rc = 0;
    freq("reset_ok", "RESET");
    printf("reset_ok_pulse\t%d %c %u\n", stub_resets, stub_reset_port ? stub_reset_port : '-',
           stub_reset_pin);

    stub_resets = 0;
    stub_reset_rc = -19; /* -ENODEV */
    freq("reset_hw", "RESET");

    stub_resets = 0;
    stub_reset_rc = 0;
    freq("reset_args", "RESET now");
    printf("reset_args_pulse\t%d\n", stub_resets);

    
    /* TRACE on every pin of the table, with a 2 Hz blink behind the stub */
    for (size_t i = 0; i < PINS_COUNT; i++) {
        char line[64], tag[80];
        stub_edges(8, TRACE_MAX_EDGES, 100000, 250000, 1);
        snprintf(line, sizeof(line), "TRACE %s 2000", PINS[i].name);
        snprintf(tag, sizeof(tag), "tracepin\t%s", PINS[i].name);
        current = tag;
        cmd_handle(line, out);
    }

    /* TRACE details, on the first wired gpio pin (if the map has one) */
    for (size_t i = 0; i < PINS_COUNT; i++) {
        char req[64];
        if (PINS[i].port == 0 || !(PINS[i].caps & CAP_GPIO)) {
            continue;
        }
        current = "trace_pin";
        out(PINS[i].name);
        snprintf(req, sizeof(req), "TRACE %s 2000", PINS[i].name);

        stub_edges(8, TRACE_MAX_EDGES, 100000, 250000, 1); /* 2 Hz blink: 100, 350 ... 1850 ms */
        freq("trace_blink", req);
        printf("trace_call\t%c %u %u\n", stub_trace_port, stub_trace_pin, stub_trace_window);

        stub_edges(0, TRACE_MAX_EDGES, 0, 0, 0); /* steady low */
        freq("trace_low", req);
        stub_edges(0, TRACE_MAX_EDGES, 0, 0, 1); /* steady high */
        freq("trace_high", req);
        stub_edges(3, TRACE_MAX_EDGES, 1, 1234567, 0); /* sub-ms values: 0.001, 1234.568 ... */
        freq("trace_fine", req);
        stub_edges(300, TRACE_MAX_EDGES, 1000, 1000, 0); /* too many to fit one line */
        freq("trace_long", req);
        stub_edges(50, 40, 1000, 1000, 0); /* buffer full but the list fits the line */
        freq("trace_bufull", req);

        stub_edges(8, TRACE_MAX_EDGES, 100000, 250000, 1);
        stub_trace_rc = TRACE_NO_PORT;
        freq("trace_noport", req);
        stub_trace_rc = TRACE_HW;
        freq("trace_hw", req);

        stub_edges(8, TRACE_MAX_EDGES, 100000, 250000, 1);
        snprintf(req, sizeof(req), "TRACE %s 0", PINS[i].name);
        freq("trace_win0", req);
        snprintf(req, sizeof(req), "TRACE %s 10001", PINS[i].name);
        freq("trace_winbig", req);
        snprintf(req, sizeof(req), "TRACE %s", PINS[i].name);
        freq("trace_args", req);
        break;
    }
    freq("trace_unknown", "TRACE D99 100");

    /* the generated pin table */
    current = "pins";
    for (size_t i = 0; i < PINS_COUNT; i++) {
        printf("pin\t%s %c %u %lu\n", PINS[i].name, PINS[i].port ? PINS[i].port : '-',
               (unsigned)PINS[i].pin, (unsigned long)PINS[i].caps);
    }
    return 0;
}