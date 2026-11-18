/*
 * PC test harness for the plain-C firmware parts: reply.c, cmd.c, pins_table.c and the
 * generated pins_gen.h. Built and run by tests/firmware/test_reply_c.py, which compares
 * every line with what grader.protocol produces for the same values.
 *
 * Output: one "<case>\t<reply line>" per case, "pin\t..." per pin-table row and
 * "freqpin\t<name>\t<reply line>" for FREQ on every pin in the table.
 */
#include <stdbool.h>
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
#include "student_uart.h"
#include "trace.h"

/* what the stubs below were asked to do, in order ("delay_start drive uart_finish ..."),
   so the ARM/COLLECT tests can check that measurements start before the stimulus */
static char events[512];

static void event(const char *e) {
    size_t n = strlen(events);
    snprintf(events + n, sizeof(events) - n, "%s%s", n ? " " : "", e);
}

/* student_uart.c is Zephyr + USART hardware; these stand-ins record the call ("-" if none
   was made) and return a canned READ result. */
static struct su_raw stub_uart;
static int stub_uart_rc;
static char stub_uart_call[64];

int su_send(char port, uint8_t pin, uint32_t baud, const uint8_t *data, size_t n) {
    /* "send <port> <pin> <baud> <n> <first 8 bytes in hex>" */
    int k = snprintf(stub_uart_call, sizeof(stub_uart_call), "send %c %u %u %u ", port, pin,
                     (unsigned)baud, (unsigned)n);
    for (size_t i = 0; i < n && i < 8; i++) {
        k += snprintf(stub_uart_call + k, sizeof(stub_uart_call) - (size_t)k, "%02X", data[i]);
    }
    return stub_uart_rc;
}

int su_read_start(char port, uint8_t pin, uint32_t baud, uint32_t window_ms) {
    snprintf(stub_uart_call, sizeof(stub_uart_call), "read %c %u %u %u", port, pin,
             (unsigned)baud, (unsigned)window_ms);
    event("uart_start");
    return stub_uart_rc;
}

int su_read_finish(struct su_raw *out) {
    event("uart_finish");
    *out = stub_uart;
    return SU_OK;
}

void su_read_cancel(void) {
    event("uart_cancel");
}

/* `n` bytes received, the first `stored` of them kept, `fe` with framing errors */
static void stub_uart_bytes(const void *bytes, uint32_t n, uint32_t stored, uint32_t fe) {
    stub_uart_rc = SU_OK;
    stub_uart.byte_count = n;
    stub_uart.stored = stored;
    stub_uart.framing_errors = fe;
    stub_uart.overruns = 0;
    memcpy(stub_uart.data, bytes, stored);
}

/* delay.c is Zephyr + GPIO interrupts; this stand-in records the call ("-" if none was
   made) and returns a canned result. */
static struct delay_raw stub_delay;
static int stub_delay_rc;
static char stub_delay_call[64];

int delay_start(const struct delay_pin *from, const struct delay_pin *to, uint32_t timeout_ms) {
    snprintf(stub_delay_call, sizeof(stub_delay_call), "%c %u %u %d > %c %u %u %d / %u",
             from->port, from->pin, from->edge, from->keep, to->port, to->pin, to->edge, to->keep,
             (unsigned)timeout_ms);
    event("delay_start");
    /* set-up problems show at the start, a missing trigger at the finish */
    return stub_delay_rc == DELAY_NO_TRIGGER ? DELAY_OK : stub_delay_rc;
}

int delay_finish(struct delay_raw *out) {
    event("delay_finish");
    *out = stub_delay;
    return stub_delay_rc == DELAY_NO_TRIGGER ? DELAY_NO_TRIGGER : DELAY_OK;
}

void delay_cancel(void) {
    event("delay_cancel");
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
    event("drive");
    return stub_drive_rc;
}

int drive_pulse(char port, uint8_t pin, int level, uint32_t width_ms) {
    snprintf(stub_drive_call, sizeof(stub_drive_call), "pulse %c %u %d %u", port, pin, level,
             (unsigned)width_ms);
    event("drive");
    return stub_drive_rc;
}

int drive_bounce(char port, uint8_t pin, uint32_t count, uint32_t interval_us, int final_level) {
    snprintf(stub_drive_call, sizeof(stub_drive_call), "bounce %c %u %u %u %d", port, pin,
             (unsigned)count, (unsigned)interval_us, final_level);
    event("drive");
    return stub_drive_rc;
}

/* trace.c is Zephyr + GPIO interrupts; this stand-in returns canned edge lists. */
static struct trace_raw stub_trace;
static struct trace_raw *stub_trace_out;
static int stub_trace_rc;
static char stub_trace_port;
static unsigned stub_trace_pin, stub_trace_window;
static int stub_trace_keep = -1;

int trace_start(char port, uint8_t pin, bool keep, uint32_t window_ms, struct trace_raw *out) {
    stub_trace_port = port;
    stub_trace_pin = pin;
    stub_trace_window = window_ms;
    stub_trace_keep = keep;
    stub_trace_out = out;
    event("trace_start");
    return stub_trace_rc;
}

int trace_finish(void) {
    event("trace_finish");
    *stub_trace_out = stub_trace;
    return TRACE_OK;
}

void trace_cancel(void) {
    event("trace_cancel");
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

int capture_start(char port, uint8_t pin, uint32_t window_ms) {
    stub_port = port;
    stub_pin = pin;
    stub_window = window_ms;
    event("freq_start");
    return stub_rc;
}

int capture_finish(struct capture_raw *out) {
    event("freq_finish");
    *out = stub_raw;
    return CAPTURE_OK;
}

void capture_cancel(void) {
    event("freq_cancel");
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


/* run one UART request (lines up to ~1.1 KB), then print the call ("-" = none) */
static void uart_case(const char *name, const char *request) {
    static char line[1200];
    current = name;
    strcpy(stub_uart_call, "-");
    snprintf(line, sizeof(line), "%s", request);
    cmd_handle(line, out);
    printf("%s_call\t%s\n", name, stub_uart_call);
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

    
    /* UART READ */
    {
        static uint8_t big[SU_RX_MAX];
        static char req[1200];

        stub_uart_bytes("ON\r\n", 4, 4, 0);
        uart_case("uart_read_on", "UART 9600 READ 200");
        stub_uart_bytes("", 0, 0, 0);
        uart_case("uart_read_empty", "UART 9600 READ 200");
        stub_uart_bytes("\xff\x00\xf0", 3, 3, 2); /* wrong baud: junk and framing errors */
        uart_case("uart_read_garbage", "UART 115200 READ 100");
        stub_uart_bytes("a,b\"c%d e", 9, 9, 0);
        uart_case("uart_read_escape", "UART 9600 READ 100");

        for (size_t i = 0; i < 1000; i++) { /* more text than a line holds */
            big[i] = (uint8_t)('A' + i % 26);
        }
        stub_uart_bytes(big, 1000, 1000, 0);
        uart_case("uart_read_long", "UART 9600 READ 1000");
        memset(big, '\n', 600); /* 3 characters each on the wire */
        stub_uart_bytes(big, 600, 600, 0);
        uart_case("uart_read_long_esc", "UART 9600 READ 1000");
        stub_uart_bytes("ONOFFON", 30, 7, 0); /* the firmware's buffer was full */
        uart_case("uart_read_bufull", "UART 9600 READ 1000");

        stub_uart_bytes("ON", 2, 2, 0);
        stub_uart.overruns = 1;
        uart_case("uart_read_overrun", "UART 9600 READ 100");
        stub_uart_bytes("ON", 2, 2, 0);
        stub_uart_rc = SU_NO_USART;
        uart_case("uart_read_nousart", "UART 9600 READ 100");
        stub_uart_rc = SU_HW;
        uart_case("uart_read_hw", "UART 9600 READ 100");

        stub_uart_bytes("ON", 2, 2, 0);
        uart_case("uart_read_w0", "UART 9600 READ 0");
        uart_case("uart_read_wbig", "UART 9600 READ 10001");
        uart_case("uart_read_wsyntax", "UART 9600 READ 1e3");

        /* every standard baud, and some that aren't */
        static const unsigned bauds[] = {300,  1200,  2400,  4800,   9600,
                                         19200, 38400, 57600, 115200, 230400};
        for (size_t i = 0; i < sizeof(bauds) / sizeof(bauds[0]); i++) {
            char name[32];
            snprintf(name, sizeof(name), "uart_baud_%u", bauds[i]);
            snprintf(req, sizeof(req), "UART %u READ 100", bauds[i]);
            uart_case(name, req);
        }
        uart_case("uart_baud_bad", "UART 9601 READ 100");
        uart_case("uart_baud_zero", "UART 0 READ 100");
        uart_case("uart_baud_big", "UART 460800 READ 100");
        uart_case("uart_baud_syntax", "UART 9600.0 READ 100");
        uart_case("uart_mode_bad", "UART 9600 WRITE 100");
        uart_case("uart_mode_lower", "UART 9600 read 100");
        uart_case("uart_args", "UART 9600 READ");

        /* UART SEND */
        stub_uart_rc = SU_OK;
        uart_case("uart_send_on", "UART 9600 SEND 4F4E0A");
        uart_case("uart_send_lower", "UART 115200 SEND 0a0d");
        uart_case("uart_send_odd", "UART 9600 SEND 4F4");
        uart_case("uart_send_nothex", "UART 9600 SEND 4G");
        uart_case("uart_send_0x", "UART 9600 SEND 0x4F");

        int k = snprintf(req, sizeof(req), "UART 9600 SEND ");
        for (int i = 0; i < 500; i++) { /* the most a request line can carry */
            k += snprintf(req + k, sizeof(req) - (size_t)k, "%02X", i & 0xFF);
        }
        uart_case("uart_send_big", req);
        k = snprintf(req, sizeof(req), "UART 9600 SEND ");
        for (int i = 0; i < 513; i++) { /* more than the payload buffer */
            k += snprintf(req + k, sizeof(req) - (size_t)k, "41");
        }
        uart_case("uart_send_toobig", req);

        stub_uart_rc = SU_NO_USART;
        uart_case("uart_send_nousart", "UART 9600 SEND 4F4E");
        stub_uart_rc = SU_HW;
        uart_case("uart_send_hw", "UART 9600 SEND 4F4E");
    }

    /* ARM / COLLECT. Pins: the first two wired timer_capture pins and the first wired
       drive pin */
    {
        const char *cap1 = NULL, *cap2 = NULL, *drv = NULL;
        for (size_t i = 0; i < PINS_COUNT; i++) {
            if (PINS[i].port == 0) {
                continue;
            }
            if (PINS[i].caps & CAP_TIMER_CAPTURE) {
                if (cap1 == NULL) {
                    cap1 = PINS[i].name;
                }
                else if (cap2 == NULL) {
                    cap2 = PINS[i].name;
                }
            }
            if (drv == NULL && (PINS[i].caps & CAP_DRIVE) && (PINS[i].caps & CAP_GPIO)) {
                drv = PINS[i].name;
            }
        }
        if (cap1 != NULL && cap2 != NULL && drv != NULL) {
            char req[96];
            printf("arm_pins\t%s %s %s\n", cap1, cap2, drv);

            /* TRACE leaves a pin the board drives alone, so it can watch the board's DRIVE */
            stub_edges(8, TRACE_MAX_EDGES, 100000, 250000, 1);
            snprintf(req, sizeof(req), "TRACE %s 100", drv);
            freq("trace_drv", req);
            printf("trace_drv_keep\t%d\n", stub_trace_keep);
            snprintf(req, sizeof(req), "TRACE %s 100", cap1);
            freq("trace_in", req);
            printf("trace_in_keep\t%d\n", stub_trace_keep);

            /* the button sequence: arm DELAY and UART READ, press, collect both */
            events[0] = '\0';
            stub_delay_result(260000, 1); /* 3.25 ms */
            stub_uart_bytes("ON\r\n", 4, 4, 0);
            stub_drive_rc = DRIVE_OK;
            snprintf(req, sizeof(req), "ARM DELAY %s FALLING %s ANY 100", drv, cap1);
            freq("arm_delay", req);
            freq("arm_uart", "ARM UART 9600 READ 200");
            snprintf(req, sizeof(req), "DRIVE %s BOUNCE 5 200 LOW", drv);
            freq("arm_press", req);
            freq("collect_delay", "COLLECT 0");
            freq("collect_uart", "COLLECT 1");
            printf("arm_button_events\t%s\n", events);
            printf("arm_button_delay_call\t%s\n", stub_delay_call);

            /* a collected slot is free again */
            stub_signal(80000000u, 100, 80000, 20000);
            snprintf(req, sizeof(req), "ARM FREQ %s 100", cap1);
            freq("arm_freq", req);
            freq("collect_freq", "COLLECT 0");
            freq("collect_again", "COLLECT 0");

            /* BUSY: a second measurement of the same kind, or on a pin in use */
            stub_edges(8, TRACE_MAX_EDGES, 100000, 250000, 1);
            snprintf(req, sizeof(req), "ARM TRACE %s 2000", cap2);
            freq("arm_trace", req);
            snprintf(req, sizeof(req), "ARM TRACE %s 100", cap1);
            freq("busy_kind", req);
            snprintf(req, sizeof(req), "TRACE %s 100", cap1);
            freq("busy_kind_now", req);
            snprintf(req, sizeof(req), "ARM FREQ %s 100", cap2);
            freq("busy_pin", req);
            snprintf(req, sizeof(req), "ARM DELAY %s FALLING %s ANY 100", drv, cap2);
            freq("busy_pin_delay", req);
            snprintf(req, sizeof(req), "FREQ %s 100", cap1);
            freq("free_other", req); /* other hardware: runs next to the armed TRACE */
            freq("collect_trace", "COLLECT 0");

            /* UART SEND while a READ is armed: same baud only */
            stub_uart_bytes("ON", 2, 2, 0);
            freq("arm_uart2", "ARM UART 9600 READ 200");
            uart_case("send_same_baud", "UART 9600 SEND 4F4E");
            uart_case("send_other_baud", "UART 115200 SEND 4F4E");

            /* RESET stops every armed measurement and frees the slots */
            snprintf(req, sizeof(req), "ARM TRACE %s 100", cap2);
            freq("arm_trace2", req);
            events[0] = '\0';
            stub_reset_rc = 0;
            freq("arm_reset", "RESET");
            printf("arm_reset_events\t%s\n", events);
            freq("collect_after_reset", "COLLECT 0");

            /* a measurement's own error arrives at COLLECT */
            stub_delay_result(0, 0);
            stub_delay_rc = DELAY_NO_TRIGGER;
            snprintf(req, sizeof(req), "ARM DELAY %s FALLING %s ANY 100", drv, cap1);
            freq("arm_notrig", req);
            freq("collect_notrig", "COLLECT 0");
            stub_delay_rc = DELAY_OK;

            /* ARM errors take no slot */
            freq("arm_none", "ARM");
            snprintf(req, sizeof(req), "ARM DRIVE %s HIGH", drv);
            freq("arm_drive", req);
            freq("arm_send", "ARM UART 9600 SEND 4F4E");
            snprintf(req, sizeof(req), "ARM ARM FREQ %s 100", cap1);
            freq("arm_arm", req);
            freq("arm_unknown", "ARM JUMP 1");
            snprintf(req, sizeof(req), "ARM FREQ %s", cap1);
            freq("arm_arity", req);
            snprintf(req, sizeof(req), "ARM FREQ %s 0", cap1);
            freq("arm_badarg", req);
            freq("arm_badpin", "ARM FREQ D99 100");
            stub_signal(80000000u, 100, 80000, 20000);
            snprintf(req, sizeof(req), "ARM FREQ %s 100", cap1);
            freq("arm_after_errors", req);
            freq("collect_bad", "COLLECT 4");
            freq("collect_word", "COLLECT x");
            freq("collect_none", "COLLECT");
            freq("arm_cleanup", "COLLECT 0");
        }
    }

    /* the generated pin table */
    current = "pins";
    for (size_t i = 0; i < PINS_COUNT; i++) {
        printf("pin\t%s %c %u %lu\n", PINS[i].name, PINS[i].port ? PINS[i].port : '-',
               (unsigned)PINS[i].pin, (unsigned long)PINS[i].caps);
    }
    return 0;
}