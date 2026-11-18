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
#include "drive.h"
#include "delay.h"
#include "pins_gen.h"
#include "reply.h"
#include "rig.h"
#include "trace.h"


/* delay.c is Zephyr + GPIO interrupts; this stand-in records the call ("-" if none was
   made) and returns a canned result. */
static struct delay_raw stub_delay;
static int stub_delay_rc;
static char stub_delay_call[64];

int delay_measure(const struct delay_pin *from, const struct delay_pin *to, uint32_t timeout_ms,
                  struct delay_raw *out) {
    snprintf(stub_delay_call, sizeof(stub_delay_call), "%c %u %u %d > %c %u %u %d / %u",
             from->port, from->pin, from->edge, from->keep, to->port, to->pin, to->edge, to->keep,
             (unsigned)timeout_ms);
    *out = stub_delay;
    return stub_delay_rc;
}

/* the first response `delay_ticks` after the trigger, `count` responses in all */
static void stub_delay_result(uint32_t delay_ticks, uint32_t count) {
    stub_delay_rc = DELAY_OK;
    stub_delay.clock_hz = 80000000u;
    stub_delay.trigger = 4294000000u; /* just before the 32-bit wrap: the delay must not care */
    stub_delay.first = stub_delay.trigger + delay_ticks;
    stub_delay.to_count = count;
}

/* drive.c is Zephyr + GPIO; these stand-ins record the call (or "-" if none was made). */
static char stub_drive_call[64];
static int stub_drive_rc;

int drive_set(char port, uint8_t pin, int level) {
    snprintf(stub_drive_call, sizeof(stub_drive_call), "set %c %u %d", port, pin, level);
    return stub_drive_rc;
}

int drive_pulse(char port, uint8_t pin, int level, uint32_t width_ms) {
    snprintf(stub_drive_call, sizeof(stub_drive_call), "pulse %c %u %d %u", port, pin, level,
             (unsigned)width_ms);
    return stub_drive_rc;
}

int drive_bounce(char port, uint8_t pin, uint32_t count, uint32_t interval_us, int final_level) {
    snprintf(stub_drive_call, sizeof(stub_drive_call), "bounce %c %u %u %u %d", port, pin,
             (unsigned)count, (unsigned)interval_us, final_level);
    return stub_drive_rc;
}

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

    
    /* DRIVE HIGH on every pin of the table */
    for (size_t i = 0; i < PINS_COUNT; i++) {
        char line[64], tag[80];
        stub_drive_rc = DRIVE_OK;
        snprintf(line, sizeof(line), "DRIVE %s HIGH", PINS[i].name);
        snprintf(tag, sizeof(tag), "drivepin\t%s", PINS[i].name);
        current = tag;
        cmd_handle(line, out);
    }

    /* DRIVE details, on the first wired drive pin (if the map has one). Each case prints
       the reply, then the call the firmware made ("-" = none) */
    for (size_t i = 0; i < PINS_COUNT; i++) {
        static const char *const cases[][3] = {
            /* name, arguments after the pin, rc of the stub */
            {"drive_high", "HIGH", "0"},
            {"drive_low", "LOW", "0"},
            {"drive_release", "RELEASE", "0"},
            {"drive_pulse", "PULSE 50 LOW", "0"},
            {"drive_bounce", "BOUNCE 5 200 LOW", "0"},
            {"drive_bounce_max", "BOUNCE 100 100000 HIGH", "0"},
            {"drive_badlevel", "MAYBE", "0"},
            {"drive_lowercase", "high", "0"},
            {"drive_pulse_release", "PULSE 50 RELEASE", "0"},
            {"drive_pulse_w0", "PULSE 0 LOW", "0"},
            {"drive_pulse_wbig", "PULSE 10001 LOW", "0"},
            {"drive_pulse_args", "PULSE 50", "0"},
            {"drive_bounce_c0", "BOUNCE 0 200 LOW", "0"},
            {"drive_bounce_cbig", "BOUNCE 101 200 LOW", "0"},
            {"drive_bounce_i9", "BOUNCE 5 9 LOW", "0"},
            {"drive_bounce_ibig", "BOUNCE 5 100001 LOW", "0"},
            {"drive_bounce_args", "BOUNCE 5 200", "0"},
            {"drive_extra", "HIGH NOW", "0"},
            {"drive_noport", "HIGH", "-1"},
            {"drive_hw", "BOUNCE 5 200 LOW", "-2"},
        };
        if (PINS[i].port == 0 || !(PINS[i].caps & CAP_DRIVE)) {
            continue;
        }
        current = "drive_pin";
        out(PINS[i].name);
        for (size_t k = 0; k < sizeof(cases) / sizeof(cases[0]); k++) {
            char req[96];
            snprintf(req, sizeof(req), "DRIVE %s %s", PINS[i].name, cases[k][1]);
            stub_drive_rc = cases[k][2][0] == '-' ? -(cases[k][2][1] - '0') : 0;
            strcpy(stub_drive_call, "-");
            freq(cases[k][0], req);
            printf("%s_call\t%s\n", cases[k][0], stub_drive_call);
        }
        break;
    }
    freq("drive_unknown", "DRIVE D99 HIGH");
    freq("drive_noargs", "DRIVE D2");

    /* DELAY: reference pins for the per-pin rows. from = first wired gpio pin, to = first
       wired timer_capture pin */
    {
        const char *from_ref = NULL, *to_ref = NULL;
        for (size_t i = 0; i < PINS_COUNT; i++) {
            if (PINS[i].port == 0) {
                continue;
            }
            if (from_ref == NULL && (PINS[i].caps & CAP_GPIO)) {
                from_ref = PINS[i].name;
            }
            if (to_ref == NULL && (PINS[i].caps & CAP_TIMER_CAPTURE)) {
                to_ref = PINS[i].name;
            }
        }
        if (from_ref != NULL && to_ref != NULL) {
            current = "delay_refs";
            printf("delay_refs\t%s %s\n", from_ref, to_ref);
            stub_delay_result(260000, 1); /* 3.25 ms */
            for (size_t i = 0; i < PINS_COUNT; i++) {
                char line[96], tag[80];
                snprintf(line, sizeof(line), "DELAY %s FALLING %s ANY 100", PINS[i].name, to_ref);
                snprintf(tag, sizeof(tag), "delayfrom\t%s", PINS[i].name);
                current = tag;
                cmd_handle(line, out);
                snprintf(line, sizeof(line), "DELAY %s FALLING %s ANY 100", from_ref, PINS[i].name);
                snprintf(tag, sizeof(tag), "delayto\t%s", PINS[i].name);
                current = tag;
                cmd_handle(line, out);
            }
        }
    }

    /* DELAY details: from = first wired drive pin (else gpio pin), to = first wired
       timer_capture pin. Each case prints the reply, then the call ("-" = none) */
    {
        const char *from = NULL, *to = NULL, *gpio = NULL;
        for (size_t i = 0; i < PINS_COUNT; i++) {
            if (PINS[i].port == 0) {
                continue;
            }
            if (from == NULL && (PINS[i].caps & CAP_DRIVE) && (PINS[i].caps & CAP_GPIO)) {
                from = PINS[i].name;
            }
            if (gpio == NULL && (PINS[i].caps & CAP_GPIO)) {
                gpio = PINS[i].name;
            }
            if (to == NULL && (PINS[i].caps & CAP_TIMER_CAPTURE)) {
                to = PINS[i].name;
            }
        }
        if (from == NULL) {
            from = gpio;
        }
        if (from != NULL && to != NULL) {
            static const struct {
                const char *name, *args; /* args: "<from_edge> <to_edge> <timeout>" */
                uint32_t ticks, count;
                int rc;
                uint32_t clock_hz;
            } cases[] = {
                {"delay_basic", "FALLING ANY 100", 260000, 1, DELAY_OK, 80000000u},
                {"delay_rising", "RISING FALLING 50", 260000, 1, DELAY_OK, 80000000u},
                {"delay_any", "ANY RISING 20", 260000, 1, DELAY_OK, 80000000u},
                {"delay_fine", "FALLING ANY 100", 99, 1, DELAY_OK, 80000000u},
                {"delay_long", "FALLING ANY 10000", 799999920u, 1, DELAY_OK, 80000000u},
                {"delay_bounce", "FALLING ANY 100", 32000, 5, DELAY_OK, 80000000u},
                {"delay_null", "FALLING ANY 100", 0, 0, DELAY_OK, 80000000u},
                {"delay_notrigger", "FALLING ANY 100", 0, 0, DELAY_NO_TRIGGER, 80000000u},
                {"delay_notrigger_long", "RISING ANY 2000", 0, 0, DELAY_NO_TRIGGER, 80000000u},
                {"delay_noport", "FALLING ANY 100", 0, 0, DELAY_NO_PORT, 80000000u},
                {"delay_hw", "FALLING ANY 100", 0, 0, DELAY_HW, 80000000u},
                {"delay_clock0", "FALLING ANY 100", 260000, 1, DELAY_OK, 0},
                {"delay_badfrom", "DOWN ANY 100", 0, 0, DELAY_OK, 80000000u},
                {"delay_badto", "FALLING rising 100", 0, 0, DELAY_OK, 80000000u},
                {"delay_t0", "FALLING ANY 0", 0, 0, DELAY_OK, 80000000u},
                {"delay_tbig", "FALLING ANY 10001", 0, 0, DELAY_OK, 80000000u},
                {"delay_tnan", "FALLING ANY 1e3", 0, 0, DELAY_OK, 80000000u},
            };
            current = "delay_pins";
            printf("delay_pins\t%s %s\n", from, to);
            for (size_t k = 0; k < sizeof(cases) / sizeof(cases[0]); k++) {
                char req[96], e1[16], e2[16], tmo[16];
                sscanf(cases[k].args, "%15s %15s %15s", e1, e2, tmo);
                snprintf(req, sizeof(req), "DELAY %s %s %s %s %s", from, e1, to, e2, tmo);
                stub_delay_result(cases[k].ticks, cases[k].count);
                stub_delay_rc = cases[k].rc;
                stub_delay.clock_hz = cases[k].clock_hz;
                strcpy(stub_delay_call, "-");
                freq(cases[k].name, req);
                printf("%s_call\t%s\n", cases[k].name, stub_delay_call);
            }
            char req[96];
            snprintf(req, sizeof(req), "DELAY %s FALLING %s ANY", from, to);
            freq("delay_args", req);
            snprintf(req, sizeof(req), "DELAY %s FALLING D99 ANY 100", from);
            freq("delay_unknown_to", req);
        }
    }
    freq("delay_unknown_from", "DELAY D99 FALLING D13 ANY 100");

    /* the generated pin table */
    current = "pins";
    for (size_t i = 0; i < PINS_COUNT; i++) {
        printf("pin\t%s %c %u %lu\n", PINS[i].name, PINS[i].port ? PINS[i].port : '-',
               (unsigned)PINS[i].pin, (unsigned long)PINS[i].caps);
    }
    return 0;
}