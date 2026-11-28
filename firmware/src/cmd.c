#include "cmd.h"

#include <stdio.h>
#include <string.h>

#include "capture.h"
#include "dac_out.h"
#include "delay.h"
#include "drive.h"
#include "pins.h"
#include "reply.h"
#include "rig.h"
#include "student_uart.h"
#include "trace.h"
#include "version.h"

// most tokens a request can have (including the verb)
#define MAX_ARGS 16

// Size of the buffer for formatted error messages (reply_err adds "ERR <CODE> ")
#define REPLY_MAX 128

// measurements that can be armed at once (protocol: at least 4)
#define ARM_SLOTS 4

// struct for the args ()
struct args {
    int argc;               // number of tokens. including the verb
    char* argv[MAX_ARGS];   // pointer to the start of each token
};

// function to send its one reply through
typedef void (*handler_fn)(const struct args *a, reply_fn reply);

// the measurements: each one can run on its own (FREQ ...) or be armed (ARM FREQ ...)
enum meas_kind {
    M_NONE = -1,    // not a measurement (PING, DRIVE, ...)
    M_FREQ,
    M_TRACE,
    M_DELAY,
    M_UART,         // UART READ
    M_KINDS,
};

// One row of the command table: which verb, how many arguments it accepts, and which function handles it.
struct command {
    const char* verb;       // verb: PING, FREQ, etc.
    int min_args;           // fewest args after the vern
    int max_args;           // most args after the verb
    handler_fn handler;     // function called when the verb matches and the count is OK
    int meas;               // enum meas_kind: which measurement ARM starts for this verb
};

// One running measurement: what it uses (to refuse a second one that would share the
// hardware) and what its finish half needs to build the reply
struct meas {
    enum meas_kind kind;
    const struct pin_def* pins[2];  // pins it watches (NULL = unused)
    bool exti;                      // it watches them with edge interrupts (EXTI lines)
    uint32_t ms;                    // DELAY: timeout_ms
    uint32_t baud;                  // UART READ: baud
    char edge[8];                   // DELAY: from_edge as sent (for the TIMEOUT message)
};

// armed measurements, by slot number (freed by COLLECT and RESET)
static struct meas slots[ARM_SLOTS];
static bool slot_used[ARM_SLOTS];

static const char* const kind_names[M_KINDS] = {"FREQ", "TRACE", "DELAY", "UART READ"};


// ---------------------- handlers -----------------------------

// liveness and version check (host sends it on connect and after a T.O. to make sure the board is answering)
// also reports the pin-map hash so the host can check the firmware was built from the same config/pinmap.yaml
static void cmd_ping(const struct args *a, reply_fn reply){
    
    struct reply_buf r;
    (void) a;

    reply_begin(&r);
    reply_str(&r, "fw", (const uint8_t *)FW_VERSION, strlen(FW_VERSION));
    reply_str(&r, "protocol", (const uint8_t *)PROTOCOL_VERSION, strlen(PROTOCOL_VERSION));
    reply_str(&r, "pinmap", (const uint8_t *)pins_map_hash, strlen(pins_map_hash));
    reply_send(&r, reply);
}

// parse a plain decimal number (no sign, spaces or other characters); false if invalid or > max
static bool parse_u32(const char* s, uint32_t max, uint32_t* out){

    uint64_t v = 0;
    if (*s == '\0'){
        return false;
    }
    for (; *s != '\0'; s++){
        if (*s < '0' || *s > '9'){
            return false;
        }
        v = v * 10 + (uint64_t)(*s - '0');
        if (v > max){
            return false;
        }
    }
    *out = (uint32_t)v;
    return true;
}

// (num + den/2) / den: integer division rounded to nearest
static uint64_t div_round(uint64_t num, uint64_t den){
    return (num + den / 2) / den;
}

// ERR BUSY if a new measurement would share hardware with an armed one: the same kind
// (each module runs one at a time), the same pin, or, when both use edge interrupts, the
// same EXTI line (the STM32 has one per pin number: PA3 and PB3 share line 3)
static bool hardware_free(const struct meas *m, reply_fn reply){

    char msg[REPLY_MAX];
    for (int s = 0; s < ARM_SLOTS; s++){
        if (!slot_used[s]){
            continue;
        }
        const struct meas *o = &slots[s];
        if (o->kind == m->kind){
            snprintf(msg, sizeof(msg), "%s is already armed in slot %d", kind_names[m->kind], s);
            reply_err(reply, "BUSY", msg);
            return false;
        }
        for (int i = 0; i < 2; i++){
            for (int j = 0; j < 2; j++){
                const struct pin_def *mine = m->pins[i], *theirs = o->pins[j];
                if (mine == NULL || theirs == NULL){
                    continue;
                }
                if (mine == theirs){
                    snprintf(msg, sizeof(msg), "pin %.16s is in use by slot %d", mine->name, s);
                    reply_err(reply, "BUSY", msg);
                    return false;
                }
                if (m->exti && o->exti && mine->pin == theirs->pin){
                    snprintf(msg, sizeof(msg), "pin %.16s shares edge interrupt line %u with slot %d",
                             mine->name, (unsigned)mine->pin, s);
                    reply_err(reply, "BUSY", msg);
                    return false;
                }
            }
        }
    }
    return true;
}

// FREQ <pin> <window_ms>: frequency and duty cycle of the signal on <pin> over the window
//   frequency_hz = (rising edges - 1) / (time from first to last rising edge)
//   duty_pct     = average high time / average period
//   edge_count   = rising edges in the window
// Fewer than 2 rising edges is a valid "no signal" result: frequency and duty are null.
static bool freq_start(const struct args *a, struct meas *m, reply_fn reply){

    char msg[REPLY_MAX];
    const char* name = a->argv[1];
    const struct pin_def* p = pins_find(name);
    uint32_t window_ms;

    if (p == NULL){
        snprintf(msg, sizeof(msg), "pin %.16s is not in the pin map", name);
        reply_err(reply, "BADPIN", msg);
        return false;
    }
    if (!pins_can_capture(p)){
        snprintf(msg, sizeof(msg), "pin %.16s has no timer_capture capability", name);
        reply_err(reply, "BADPIN", msg);
        return false;
    }
    if (!pins_wired(p)){
        snprintf(msg, sizeof(msg), "pin %.16s is not wired (TBD in the pin map)", name);
        reply_err(reply, "BADPIN", msg);
        return false;
    }
    if (!parse_u32(a->argv[2], 10000, &window_ms) || window_ms < 1){
        reply_err(reply, "BADARG", "window_ms must be 1-10000");
        return false;
    }

    m->kind = M_FREQ;
    m->pins[0] = p;
    if (!hardware_free(m, reply)){
        return false;
    }
    int rc = capture_start(p->port, p->pin, window_ms);
    if (rc == CAPTURE_NO_TIMER){
        snprintf(msg, sizeof(msg), "no capture timer on P%c%u (pin %.16s)", p->port, (unsigned)p->pin, name);
        reply_err(reply, "BADPIN", msg);
        return false;
    }
    if (rc != CAPTURE_OK){
        reply_err(reply, "INTERNAL", "capture timer setup failed");
        return false;
    }
    return true;
}

static void freq_finish(struct meas *m, reply_fn reply){

    struct capture_raw raw;
    struct reply_buf r;
    (void) m;

    if (capture_finish(&raw) != CAPTURE_OK){
        reply_err(reply, "INTERNAL", "capture timer setup failed");
        return;
    }
    // missed edges would make every number wrong: that's a rig fault, not a student fault
    if (raw.overruns != 0){
        reply_err(reply, "INTERNAL", "capture overrun: signal too fast to time every edge");
        return;
    }

    reply_begin(&r);
    uint32_t span = raw.last_rise - raw.first_rise;   // ticks, wrap-safe
    if (raw.rising >= 2 && span != 0){
        uint64_t periods = raw.rising - 1;

        // Hz with 3 decimals: clock * periods / span, times 1000
        uint64_t freq_mhz = div_round((uint64_t)raw.clock_hz * 1000u * periods, span);
        reply_fixed(&r, "frequency_hz", (int64_t)freq_mhz, 3);

        if (raw.high_count != 0){
            // average high time and period in ticks x1000, then % with 2 decimals
            uint64_t high_x1000 = div_round(raw.high_ticks * 1000u, raw.high_count);
            uint64_t period_x1000 = div_round((uint64_t)span * 1000u, periods);
            uint64_t duty_x100 = div_round(high_x1000 * 10000u, period_x1000);
            reply_fixed(&r, "duty_pct", (int64_t)duty_x100, 2);
        }
        else {
            reply_null(&r, "duty_pct");
        }
    }
    else {
        reply_null(&r, "frequency_hz");
        reply_null(&r, "duty_pct");
    }
    reply_int(&r, "edge_count", raw.rising);
    reply_send(&r, reply);
}

// WAIT <ms>: board-side delay, so all timing in a plan stays on the board (0-60000 ms).
// Replies OK once the time has passed.
static void cmd_wait(const struct args *a, reply_fn reply){

    uint32_t ms;
    struct reply_buf r;

    if (!parse_u32(a->argv[1], 60000, &ms)){
        reply_err(reply, "BADARG", "ms must be 0-60000");
        return;
    }
    rig_sleep_ms(ms);

    reply_begin(&r);
    reply_send(&r, reply);
}

// RESET: one pulse on the student board's RST line (the pin-map row with the reset
// capability). Replies OK once the line is released; the plan's WAIT gives the board time
// to boot. Every armed measurement is stopped and its slot freed first.
static void cancel_all(void);

static void cmd_reset(const struct args *a, reply_fn reply){

    char msg[REPLY_MAX];
    struct reply_buf r;
    const struct pin_def* p = pins_reset_line();
    (void) a;

    cancel_all();
    if (p == NULL){
        reply_err(reply, "BADPIN", "no reset line in the pin map");
        return;
    }
    if (!pins_wired(p)){
        snprintf(msg, sizeof(msg), "reset line %.16s is not wired (TBD in the pin map)", p->name);
        reply_err(reply, "BADPIN", msg);
        return;
    }
    if (rig_reset_pulse(p->port, p->pin) != 0){
        snprintf(msg, sizeof(msg), "could not drive reset line P%c%u", p->port, (unsigned)p->pin);
        reply_err(reply, "INTERNAL", msg);
        return;
    }

    reply_begin(&r);
    reply_send(&r, reply);
}

// TRACE <pin> <window_ms>: every edge on <pin> during the window.
//   edge_count  = edges seen (rising and falling)
//   final_level = pin level at the end of the window (0/1)
//   edges_ms    = time of each edge from the start of the window, in ms (us resolution)
// If the list doesn't fit in one reply line, or more edges came than the firmware stores,
// the list is cut short and the reply says truncated=1; edge_count is still the full count.
// On a pin the board drives (D2), TRACE leaves the pin alone and sees the board's own DRIVE.
static struct trace_raw trace_buf;            // ~1 KB: kept off the stack
static int64_t trace_us[TRACE_MAX_EDGES];     // edge times in us (= ms with 3 decimals)

static bool trace_start_cmd(const struct args *a, struct meas *m, reply_fn reply){

    char msg[REPLY_MAX];
    const char* name = a->argv[1];
    const struct pin_def* p = pins_find(name);
    uint32_t window_ms;

    if (p == NULL){
        snprintf(msg, sizeof(msg), "pin %.16s is not in the pin map", name);
        reply_err(reply, "BADPIN", msg);
        return false;
    }
    if (!pins_is_gpio(p)){
        snprintf(msg, sizeof(msg), "pin %.16s has no gpio capability", name);
        reply_err(reply, "BADPIN", msg);
        return false;
    }
    if (!pins_wired(p)){
        snprintf(msg, sizeof(msg), "pin %.16s is not wired (TBD in the pin map)", name);
        reply_err(reply, "BADPIN", msg);
        return false;
    }
    if (!parse_u32(a->argv[2], 10000, &window_ms) || window_ms < 1){
        reply_err(reply, "BADARG", "window_ms must be 1-10000");
        return false;
    }

    m->kind = M_TRACE;
    m->pins[0] = p;
    m->exti = true;
    if (!hardware_free(m, reply)){
        return false;
    }
    int rc = trace_start(p->port, p->pin, pins_can_drive(p), window_ms, &trace_buf);
    if (rc == TRACE_NO_PORT){
        snprintf(msg, sizeof(msg), "no GPIO port %c (pin %.16s)", p->port, name);
        reply_err(reply, "INTERNAL", msg);
        return false;
    }
    if (rc != TRACE_OK){
        snprintf(msg, sizeof(msg), "edge capture setup failed on P%c%u", p->port, (unsigned)p->pin);
        reply_err(reply, "INTERNAL", msg);
        return false;
    }
    return true;
}

static void trace_finish_cmd(struct meas *m, reply_fn reply){

    char msg[REPLY_MAX];
    const struct pin_def* p = m->pins[0];
    struct reply_buf r;

    if (trace_finish() != TRACE_OK || trace_buf.clock_hz == 0){
        snprintf(msg, sizeof(msg), "edge capture setup failed on P%c%u", p->port, (unsigned)p->pin);
        reply_err(reply, "INTERNAL", msg);
        return;
    }

    // ticks since the window start -> us (unsigned subtraction handles counter wrap)
    for (uint32_t i = 0; i < trace_buf.stored; i++){
        uint64_t ticks = (uint32_t)(trace_buf.t[i] - trace_buf.start);
        trace_us[i] = (int64_t)div_round(ticks * 1000000u, trace_buf.clock_hz);
    }

    reply_begin(&r);
    reply_int(&r, "edge_count", trace_buf.edge_count);
    reply_int(&r, "final_level", trace_buf.final_level);
    reply_list_fixed(&r, "edges_ms", trace_us, trace_buf.stored, 3);
    if (trace_buf.stored < trace_buf.edge_count && !r.truncated){
        reply_int(&r, "truncated", 1);   // the firmware's edge buffer filled up
    }
    reply_send(&r, reply);
}

// HIGH / LOW (/ RELEASE if allowed) -> DRIVE_*; -1 if it is none of them
static int parse_level(const char* s, bool allow_release){

    if (strcmp(s, "HIGH") == 0){
        return DRIVE_HIGH;
    }
    if (strcmp(s, "LOW") == 0){
        return DRIVE_LOW;
    }
    if (allow_release && strcmp(s, "RELEASE") == 0){
        return DRIVE_RELEASE;
    }
    return -1;
}

// DRIVE <pin> HIGH|LOW|RELEASE
// DRIVE <pin> PULSE <width_ms> HIGH|LOW
// DRIVE <pin> BOUNCE <count> <interval_us> HIGH|LOW
// The STM32 plays the student's input (a button). Replies OK once the action is complete.
static void cmd_drive(const struct args *a, reply_fn reply){

    char msg[REPLY_MAX];
    const char* name = a->argv[1];
    const char* action = a->argv[2];
    int n = a->argc - 1;            // arguments after the verb
    const struct pin_def* p = pins_find(name);
    struct reply_buf r;
    int rc;

    if (p == NULL){
        snprintf(msg, sizeof(msg), "pin %.16s is not in the pin map", name);
        reply_err(reply, "BADPIN", msg);
        return;
    }
    if (!pins_can_drive(p)){
        snprintf(msg, sizeof(msg), "pin %.16s has no drive capability", name);
        reply_err(reply, "BADPIN", msg);
        return;
    }
    if (!pins_wired(p)){
        snprintf(msg, sizeof(msg), "pin %.16s is not wired (TBD in the pin map)", name);
        reply_err(reply, "BADPIN", msg);
        return;
    }

    if (strcmp(action, "PULSE") == 0){
        uint32_t width_ms;
        int level;
        if (n != 4){
            reply_err(reply, "BADCMD", "usage: DRIVE <pin> PULSE <width_ms> HIGH|LOW");
            return;
        }
        if (!parse_u32(a->argv[3], 10000, &width_ms) || width_ms < 1){
            reply_err(reply, "BADARG", "width_ms must be 1-10000");
            return;
        }
        if ((level = parse_level(a->argv[4], false)) < 0){
            reply_err(reply, "BADARG", "level must be HIGH or LOW");
            return;
        }
        rc = drive_pulse(p->port, p->pin, level, width_ms);
    }
    else if (strcmp(action, "BOUNCE") == 0){
        uint32_t count, interval_us;
        int level;
        if (n != 5){
            reply_err(reply, "BADCMD", "usage: DRIVE <pin> BOUNCE <count> <interval_us> HIGH|LOW");
            return;
        }
        if (!parse_u32(a->argv[3], 100, &count) || count < 1){
            reply_err(reply, "BADARG", "count must be 1-100");
            return;
        }
        if (!parse_u32(a->argv[4], 100000, &interval_us) || interval_us < 10){
            reply_err(reply, "BADARG", "interval_us must be 10-100000");
            return;
        }
        if ((level = parse_level(a->argv[5], false)) < 0){
            reply_err(reply, "BADARG", "level must be HIGH or LOW");
            return;
        }
        rc = drive_bounce(p->port, p->pin, count, interval_us, level);
    }
    else {
        int level;
        if (n != 2){
            reply_err(reply, "BADCMD", "usage: DRIVE <pin> HIGH|LOW|RELEASE");
            return;
        }
        if ((level = parse_level(action, true)) < 0){
            reply_err(reply, "BADARG", "level must be HIGH, LOW or RELEASE");
            return;
        }
        rc = drive_set(p->port, p->pin, level);
    }

    if (rc == DRIVE_NO_PORT){
        snprintf(msg, sizeof(msg), "no GPIO port %c (pin %.16s)", p->port, name);
        reply_err(reply, "INTERNAL", msg);
        return;
    }
    if (rc != DRIVE_OK){
        snprintf(msg, sizeof(msg), "could not drive P%c%u", p->port, (unsigned)p->pin);
        reply_err(reply, "INTERNAL", msg);
        return;
    }
    reply_begin(&r);
    reply_send(&r, reply);
}

// RISING / FALLING / ANY -> DELAY_EDGE_*; 0 if it is none of them
static uint8_t parse_edge(const char* s){

    if (strcmp(s, "RISING") == 0){
        return DELAY_EDGE_RISING;
    }
    if (strcmp(s, "FALLING") == 0){
        return DELAY_EDGE_FALLING;
    }
    if (strcmp(s, "ANY") == 0){
        return DELAY_EDGE_ANY;
    }
    return 0;
}

// pin is in the map, has the capability the command needs and is wired; otherwise sends
// ERR BADPIN and returns false
static bool pin_usable(const struct pin_def* p, const char* name, bool has_cap,
                       const char* cap, reply_fn reply){

    char msg[REPLY_MAX];
    if (p == NULL){
        snprintf(msg, sizeof(msg), "pin %.16s is not in the pin map", name);
        reply_err(reply, "BADPIN", msg);
        return false;
    }
    if (!has_cap){
        snprintf(msg, sizeof(msg), "pin %.16s has no %s capability", name, cap);
        reply_err(reply, "BADPIN", msg);
        return false;
    }
    if (!pins_wired(p)){
        snprintf(msg, sizeof(msg), "pin %.16s is not wired (TBD in the pin map)", name);
        reply_err(reply, "BADPIN", msg);
        return false;
    }
    return true;
}

// DAC <pin> <mv>: output mv (0-3300) on <pin> (a pin with the dac capability) and keep
// it there, like a potentiometer or an analog sensor on the student's analog input.
// Replies OK once the output has settled. A stimulus, so it may run while measurements
// are armed.
static void cmd_dac(const struct args *a, reply_fn reply){

    char msg[REPLY_MAX];
    const char* name = a->argv[1];
    const struct pin_def* p = pins_find(name);
    uint32_t mv;
    struct reply_buf r;

    if (!pin_usable(p, name, pins_can_dac(p), "dac", reply)){
        return;
    }
    if (!parse_u32(a->argv[2], DAC_OUT_MAX_MV, &mv)){
        reply_err(reply, "BADARG", "mv must be 0-3300");
        return;
    }

    int rc = dac_out_set(p->port, p->pin, mv);
    if (rc == DAC_OUT_NO_CHANNEL){
        snprintf(msg, sizeof(msg), "no DAC output on P%c%u (pin %.16s)", p->port, (unsigned)p->pin, name);
        reply_err(reply, "BADPIN", msg);
        return;
    }
    if (rc != DAC_OUT_OK){
        reply_err(reply, "INTERNAL", "DAC setup failed");
        return;
    }
    reply_begin(&r);
    reply_send(&r, reply);
}

// DELAY <from_pin> <from_edge> <to_pin> <to_edge> <timeout_ms>   (edges: RISING|FALLING|ANY)
//   delay_ms      = time from the first from_edge on from_pin (the trigger) to the first
//                   to_edge on to_pin after it, in ms (us resolution); null if none came
//   to_edge_count = to_edges on to_pin from the trigger until timeout_ms after it
// The reply always takes the full timeout after the trigger. The trigger must come within
// max(timeout_ms, 1000 ms) of the request, otherwise ERR TIMEOUT: the rig failed to
// trigger. If from_pin is a pin the board drives, the board's own DRIVE is the trigger:
// ARM DELAY ..., then DRIVE ..., then COLLECT.
static bool delay_start_cmd(const struct args *a, struct meas *m, reply_fn reply){

    char msg[REPLY_MAX];
    const char* from_name = a->argv[1];
    const char* to_name = a->argv[3];
    const struct pin_def* from = pins_find(from_name);
    const struct pin_def* to = pins_find(to_name);
    uint8_t from_edge, to_edge;
    uint32_t timeout_ms;

    if (!pin_usable(from, from_name, pins_is_gpio(from), "gpio", reply) ||
        !pin_usable(to, to_name, pins_can_capture(to), "timer_capture", reply)){
        return false;
    }
    if ((from_edge = parse_edge(a->argv[2])) == 0){
        reply_err(reply, "BADARG", "from_edge must be RISING, FALLING or ANY");
        return false;
    }
    if ((to_edge = parse_edge(a->argv[4])) == 0){
        reply_err(reply, "BADARG", "to_edge must be RISING, FALLING or ANY");
        return false;
    }
    if (!parse_u32(a->argv[5], 10000, &timeout_ms) || timeout_ms < 1){
        reply_err(reply, "BADARG", "timeout_ms must be 1-10000");
        return false;
    }
    // the STM32 has one edge interrupt line per pin number (PA3 and PB3 share line 3)
    if (from->pin == to->pin && from->port != to->port){
        snprintf(msg, sizeof(msg), "pins %.16s and %.16s share edge interrupt line %u",
                 from_name, to_name, (unsigned)from->pin);
        reply_err(reply, "BADARG", msg);
        return false;
    }

    m->kind = M_DELAY;
    m->pins[0] = from;
    m->pins[1] = to;
    m->exti = true;
    m->ms = timeout_ms;
    snprintf(m->edge, sizeof(m->edge), "%.7s", a->argv[2]);
    if (!hardware_free(m, reply)){
        return false;
    }

    struct delay_pin f = {from->port, from->pin, from_edge, pins_can_drive(from)};
    struct delay_pin t = {to->port, to->pin, to_edge, pins_can_drive(to)};
    int rc = delay_start(&f, &t, timeout_ms);
    if (rc == DELAY_NO_PORT){
        snprintf(msg, sizeof(msg), "no GPIO port for P%c%u or P%c%u",
                 from->port, (unsigned)from->pin, to->port, (unsigned)to->pin);
        reply_err(reply, "INTERNAL", msg);
        return false;
    }
    if (rc != DELAY_OK){
        snprintf(msg, sizeof(msg), "edge interrupt setup failed on P%c%u or P%c%u",
                 from->port, (unsigned)from->pin, to->port, (unsigned)to->pin);
        reply_err(reply, "INTERNAL", msg);
        return false;
    }
    return true;
}

static void delay_finish_cmd(struct meas *m, reply_fn reply){

    char msg[REPLY_MAX];
    const struct pin_def* from = m->pins[0];
    const struct pin_def* to = m->pins[1];
    struct delay_raw raw;
    struct reply_buf r;

    int rc = delay_finish(&raw);
    if (rc == DELAY_NO_TRIGGER){
        uint32_t window_ms = m->ms > DELAY_TRIGGER_MIN_MS ? m->ms : DELAY_TRIGGER_MIN_MS;
        snprintf(msg, sizeof(msg), "no %s edge on %.16s within %u ms",
                 m->edge, from->name, (unsigned)window_ms);
        reply_err(reply, "TIMEOUT", msg);
        return;
    }
    if (rc != DELAY_OK || raw.clock_hz == 0){
        snprintf(msg, sizeof(msg), "edge interrupt setup failed on P%c%u or P%c%u",
                 from->port, (unsigned)from->pin, to->port, (unsigned)to->pin);
        reply_err(reply, "INTERNAL", msg);
        return;
    }

    reply_begin(&r);
    if (raw.to_count > 0){
        // ticks -> us (= ms with 3 decimals); unsigned subtraction handles the counter wrap
        uint64_t ticks = (uint32_t)(raw.first - raw.trigger);
        reply_fixed(&r, "delay_ms", (int64_t)div_round(ticks * 1000000u, raw.clock_hz), 3);
    }
    else {
        reply_null(&r, "delay_ms");    // to_pin never responded: a valid measurement
    }
    reply_int(&r, "to_edge_count", raw.to_count);
    reply_send(&r, reply);
}

// the student's Serial1 runs at one of these (the same list as STANDARD_BAUDS in validate.py)
static const uint32_t uart_bauds[] = {
    300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200, 230400,
};

// the uart_rx / uart_tx row of the pin map, if it is there and wired; otherwise sends
// ERR BADPIN and returns NULL
static const struct pin_def* uart_line(const struct pin_def* p, const char* cap, reply_fn reply){

    char msg[REPLY_MAX];
    if (p == NULL){
        snprintf(msg, sizeof(msg), "no %s pin in the pin map", cap);
        reply_err(reply, "BADPIN", msg);
        return NULL;
    }
    if (!pins_wired(p)){
        snprintf(msg, sizeof(msg), "%s pin %.16s is not wired (TBD in the pin map)", cap, p->name);
        reply_err(reply, "BADPIN", msg);
        return NULL;
    }
    return p;
}

// 0-15 for a hex digit (either case), -1 otherwise
static int hex_digit(char c){

    if (c >= '0' && c <= '9'){
        return c - '0';
    }
    if (c >= 'A' && c <= 'F'){
        return c - 'A' + 10;
    }
    if (c >= 'a' && c <= 'f'){
        return c - 'a' + 10;
    }
    return -1;
}

// characters a byte takes inside a reply string: 1 as it is, 3 as %XX (see reply_str)
static size_t str_cost(uint8_t b){
    return (b >= 0x21 && b <= 0x7E && b != '%' && b != '"' && b != ',') ? 1 : 3;
}

// UART <baud> ...: the baud must be one of uart_bauds; otherwise sends ERR BADARG
static bool parse_baud(const char* s, uint32_t* baud, reply_fn reply){

    if (parse_u32(s, 230400, baud)){
        for (size_t i = 0; i < sizeof(uart_bauds) / sizeof(uart_bauds[0]); i++){
            if (*baud == uart_bauds[i]){
                return true;
            }
        }
    }
    reply_err(reply, "BADARG", "baud must be 300, 1200, 2400, 4800, 9600, 19200, 38400, "
                               "57600, 115200 or 230400");
    return false;
}

// UART <baud> SEND <hex>: send the bytes to the student's Serial1 RX (8N1). OK once the
// last byte is out. Allowed while a UART READ is armed at the same baud.
static void uart_send(uint32_t baud, const char* hex, reply_fn reply){

    static uint8_t payload[PROTO_LINE_MAX / 2];
    char msg[REPLY_MAX];
    size_t len = strlen(hex);
    struct reply_buf r;

    const struct pin_def* p = uart_line(pins_uart_tx_line(), "uart_tx", reply);
    if (p == NULL){
        return;
    }
    if (len == 0 || len % 2 != 0 || len / 2 > sizeof(payload)){
        reply_err(reply, "BADARG", "payload must be hex bytes, e.g. 48690A");
        return;
    }
    for (size_t i = 0; i < len / 2; i++){
        int hi = hex_digit(hex[2 * i]);
        int lo = hex_digit(hex[2 * i + 1]);
        if (hi < 0 || lo < 0){
            reply_err(reply, "BADARG", "payload must be hex bytes, e.g. 48690A");
            return;
        }
        payload[i] = (uint8_t)(hi << 4 | lo);
    }
    // the USART has one baud for both directions
    for (int s = 0; s < ARM_SLOTS; s++){
        if (slot_used[s] && slots[s].kind == M_UART && slots[s].baud != baud){
            snprintf(msg, sizeof(msg), "UART READ at %u baud is armed in slot %d",
                     (unsigned)slots[s].baud, s);
            reply_err(reply, "BUSY", msg);
            return;
        }
    }

    int rc = su_send(p->port, p->pin, baud, payload, len / 2);
    if (rc == SU_NO_USART){
        snprintf(msg, sizeof(msg), "no USART1 on P%c%u (pin %.16s)", p->port, (unsigned)p->pin, p->name);
        reply_err(reply, "BADPIN", msg);
        return;
    }
    if (rc != SU_OK){
        reply_err(reply, "INTERNAL", "student UART setup failed");
        return;
    }
    reply_begin(&r);
    reply_send(&r, reply);
}

// UART <baud> READ <window_ms>: everything the student's Serial1 TX sends in the window.
//   text           = the raw bytes (percent-encoded on the wire)
//   byte_count     = bytes received
//   framing_errors = bytes received with a framing error (e.g. the wrong baud)
// If the text doesn't fit in one reply line, or more bytes came than the firmware stores,
// the text is cut short and truncated=1 follows it; byte_count is still the full count.
static struct su_raw uart_buf;      // ~1 KB: kept off the stack

static bool uart_read_start(const struct args *a, struct meas *m, reply_fn reply){

    char msg[REPLY_MAX];
    uint32_t baud, window_ms;

    if (!parse_baud(a->argv[1], &baud, reply)){
        return false;
    }
    if (strcmp(a->argv[2], "SEND") == 0){
        reply_err(reply, "BADCMD", "only UART READ can be armed");
        return false;
    }
    if (strcmp(a->argv[2], "READ") != 0){
        reply_err(reply, "BADARG", "mode must be SEND or READ");
        return false;
    }
    const struct pin_def* p = uart_line(pins_uart_rx_line(), "uart_rx", reply);
    if (p == NULL){
        return false;
    }
    if (!parse_u32(a->argv[3], 10000, &window_ms) || window_ms < 1){
        reply_err(reply, "BADARG", "window_ms must be 1-10000");
        return false;
    }

    m->kind = M_UART;
    m->pins[0] = p;
    m->baud = baud;
    if (!hardware_free(m, reply)){
        return false;
    }
    int rc = su_read_start(p->port, p->pin, baud, window_ms);
    if (rc == SU_NO_USART){
        snprintf(msg, sizeof(msg), "no USART1 on P%c%u (pin %.16s)", p->port, (unsigned)p->pin, p->name);
        reply_err(reply, "BADPIN", msg);
        return false;
    }
    if (rc != SU_OK){
        reply_err(reply, "INTERNAL", "student UART setup failed");
        return false;
    }
    return true;
}

static void uart_read_finish(struct meas *m, reply_fn reply){

    struct reply_buf r;
    (void) m;

    if (su_read_finish(&uart_buf) != SU_OK){
        reply_err(reply, "INTERNAL", "student UART setup failed");
        return;
    }
    // lost bytes would make the text wrong: that's a rig fault, not a student fault
    if (uart_buf.overruns != 0){
        reply_err(reply, "INTERNAL", "uart overrun: bytes arrived faster than the board read them");
        return;
    }

    // keep as many leading bytes as fit, leaving room for "OK", the quotes and the
    // other fields (" truncated=1 byte_count=<10 digits> framing_errors=<10 digits>")
    size_t budget = PROTO_LINE_MAX - 80;
    size_t n = 0, used = 0;
    while (n < uart_buf.stored && used + str_cost(uart_buf.data[n]) <= budget){
        used += str_cost(uart_buf.data[n]);
        n++;
    }

    reply_begin(&r);
    reply_str(&r, "text", uart_buf.data, n);
    if (n < uart_buf.byte_count){
        reply_int(&r, "truncated", 1);
    }
    reply_int(&r, "byte_count", uart_buf.byte_count);
    reply_int(&r, "framing_errors", uart_buf.framing_errors);
    reply_send(&r, reply);
}

// ------------------------------ start / finish / ARM / COLLECT ------------------------------
// Every measurement runs in two halves:
//   start:  check the arguments, make sure no armed measurement uses the same hardware,
//           and start it; on any problem it sends the ERR reply and returns false
//   finish: wait until the measurement is done and send its reply
// A plain request (FREQ ...) runs both halves back to back. ARM runs the start half and
// replies with a slot number at once; COLLECT runs the finish half later. In between, the
// host sends the stimulus (DRIVE, UART SEND) that the measurement should see.

struct meas_ops {
    bool (*start)(const struct args *a, struct meas *m, reply_fn reply);
    void (*finish)(struct meas *m, reply_fn reply);
    void (*cancel)(void);       // stop without a reply (RESET)
};

static const struct meas_ops ops[M_KINDS] = {
    [M_FREQ] = {freq_start, freq_finish, capture_cancel},
    [M_TRACE] = {trace_start_cmd, trace_finish_cmd, trace_cancel},
    [M_DELAY] = {delay_start_cmd, delay_finish_cmd, delay_cancel},
    [M_UART] = {uart_read_start, uart_read_finish, su_read_cancel},
};

// a plain (blocking) measurement request
static void run_now(enum meas_kind kind, const struct args *a, reply_fn reply){

    struct meas m = {0};
    if (ops[kind].start(a, &m, reply)){
        ops[kind].finish(&m, reply);
    }
}

static void cmd_freq(const struct args *a, reply_fn reply){
    run_now(M_FREQ, a, reply);
}

static void cmd_trace(const struct args *a, reply_fn reply){
    run_now(M_TRACE, a, reply);
}

static void cmd_delay(const struct args *a, reply_fn reply){
    run_now(M_DELAY, a, reply);
}

// UART <baud> SEND <hex>  |  UART <baud> READ <window_ms>
static void cmd_uart(const struct args *a, reply_fn reply){

    uint32_t baud;
    if (!parse_baud(a->argv[1], &baud, reply)){
        return;
    }
    if (strcmp(a->argv[2], "SEND") == 0){
        uart_send(baud, a->argv[3], reply);
    }
    else if (strcmp(a->argv[2], "READ") == 0){
        run_now(M_UART, a, reply);
    }
    else {
        reply_err(reply, "BADARG", "mode must be SEND or READ");
    }
}

// stop every armed measurement and free its slot (RESET)
static void cancel_all(void){

    for (int s = 0; s < ARM_SLOTS; s++){
        if (slot_used[s]){
            ops[slots[s].kind].cancel();
            slot_used[s] = false;
        }
    }
}

static const struct command* find_command(const char* verb);
static bool arity_ok(const struct command* c, int n, reply_fn reply);

// ARM <measurement request>: start the measurement in the background and reply
// OK slot=<n> at once. Its result comes from COLLECT <n>.
static void cmd_arm(const struct args *a, reply_fn reply){

    char msg[REPLY_MAX];
    struct args inner;
    struct reply_buf r;

    // the request after ARM, as if it had been sent on its own
    inner.argc = a->argc - 1;
    for (int i = 0; i < inner.argc; i++){
        inner.argv[i] = a->argv[i + 1];
    }

    const struct command* c = find_command(inner.argv[0]);
    if (c == NULL){
        snprintf(msg, sizeof(msg), "unknown verb %.32s", inner.argv[0]);
        reply_err(reply, "BADCMD", msg);
        return;
    }
    if (c->meas == M_NONE){
        snprintf(msg, sizeof(msg), "only measurements can be armed (FREQ, TRACE, DELAY, UART READ), not %.16s", c->verb);
        reply_err(reply, "BADCMD", msg);
        return;
    }
    if (!arity_ok(c, inner.argc - 1, reply)){
        return;
    }

    int s = 0;
    while (s < ARM_SLOTS && slot_used[s]){
        s++;
    }
    if (s == ARM_SLOTS){
        snprintf(msg, sizeof(msg), "all %d slots are armed", ARM_SLOTS);
        reply_err(reply, "BUSY", msg);
        return;
    }

    slots[s] = (struct meas){0};
    if (!ops[c->meas].start(&inner, &slots[s], reply)){
        return;
    }
    slot_used[s] = true;

    reply_begin(&r);
    reply_int(&r, "slot", s);
    reply_send(&r, reply);
}

// COLLECT <slot>: wait for that armed measurement to finish and reply with its normal
// result (or its error). The slot is free again afterwards.
static void cmd_collect(const struct args *a, reply_fn reply){

    char msg[REPLY_MAX];
    uint32_t s;

    if (!parse_u32(a->argv[1], ARM_SLOTS - 1, &s) || !slot_used[s]){
        snprintf(msg, sizeof(msg), "slot %.16s is not armed", a->argv[1]);
        reply_err(reply, "NOSLOT", msg);
        return;
    }
    slot_used[s] = false;
    ops[slots[s].kind].finish(&slots[s], reply);
}

// Command Table
static const struct command commands[] = {
    {"PING", 0, 0, cmd_ping, M_NONE},
    {"FREQ", 2, 2, cmd_freq, M_FREQ},
    {"WAIT", 1, 1, cmd_wait, M_NONE},
    {"RESET", 0, 0, cmd_reset, M_NONE},
    {"TRACE", 2, 2, cmd_trace, M_TRACE},
    {"DRIVE", 2, 5, cmd_drive, M_NONE},
    {"DELAY", 5, 5, cmd_delay, M_DELAY},
    {"UART", 3, 3, cmd_uart, M_UART},
    {"DAC", 2, 2, cmd_dac, M_NONE},
    {"ARM", 1, MAX_ARGS - 1, cmd_arm, M_NONE},
    {"COLLECT", 1, 1, cmd_collect, M_NONE},
};


// ------------------------------ dispatch -----------------------------------

// the table row for a verb, or NULL
static const struct command* find_command(const char* verb){

    for (size_t i = 0; i < sizeof(commands) / sizeof(commands[0]); i++){
        if (strcmp(verb, commands[i].verb) == 0){
            return &commands[i];
        }
    }
    return NULL;
}

// n arguments (not counting the verb) are allowed for c; otherwise sends ERR BADCMD
static bool arity_ok(const struct command* c, int n, reply_fn reply){

    char msg[REPLY_MAX];
    if (n >= c->min_args && n <= c->max_args){
        return true;
    }
    if (c->min_args == c->max_args){
        snprintf(msg, sizeof(msg), "%s takes %d arguments, got %d", c->verb, c->min_args, n);
    }
    else {
        snprintf(msg, sizeof(msg), "%s takes %d-%d arguments, got %d", c->verb, c->min_args, c->max_args, n);
    }
    reply_err(reply, "BADCMD", msg);
    return false;
}

// split on single or repeated spaces, returns -1 if there are too many tokens
static int split(char* line, struct args* a){

    // set the tokens to zero and iterate through the line
    a->argc = 0;
    for (char *p = line; *p != '\0';){
        
        // keep iterating until p is not a space anymore
        while (*p == ' '){
            *p++ = '\0';
        }

        // reached the end of the line, get out of loop
        if (*p == '\0'){
            break;
        }

        // p is at the start of a new token, but argv is already full
        if (a->argc == MAX_ARGS){
            return -1;
        }

        // record where this token starts and count it
        a->argv[a->argc++] = p;
        
        // move p past the token to the next space or the end of the line
        while (*p != '\0' && *p != ' '){
            p++;
        }
    }
    return 0;
}

// Handle one request line: split it, find the verb in the commands, check number of args, and call the handler
void cmd_handle(char* line, reply_fn reply){

    // buffer for building the message and the split request (a)
    char msg[REPLY_MAX];
    struct args a;

    // checking the line
    if(split(line, &a) < 0){
        reply_err(reply, "BADCMD", "too many arguments");
        return;
    }

    // check to see if there are blank lines or a line of only spaces
    if (a.argc == 0){
        reply_err(reply, "BADCMD", "empty request");
        return;
    }

    const struct command *c = find_command(a.argv[0]);
    if (c == NULL){
        snprintf(msg, sizeof(msg), "unknown verb %.32s", a.argv[0]);
        reply_err(reply, "BADCMD", msg);
        return;
    }

    // verb and arg count are valid: handler checks the args
    if (arity_ok(c, a.argc - 1, reply)){
        c->handler(&a, reply);
    }
}