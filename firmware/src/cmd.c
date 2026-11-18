#include "cmd.h"

#include <stdio.h>
#include <string.h>

#include "capture.h"
#include "delay.h"
#include "drive.h"
#include "pins.h"
#include "reply.h"
#include "rig.h"
#include "trace.h"
#include "version.h"

// most tokens a request can have (including the verb)
#define MAX_ARGS 16

// Size of the buffer for formatted error messages (reply_err adds "ERR <CODE> ")
#define REPLY_MAX 128

// struct for the args ()
struct args {
    int argc;               // number of tokens. including the verb
    char* argv[MAX_ARGS];   // pointer to the start of each token
};

// function to send its one reply through
typedef void (*handler_fn)(const struct args *a, reply_fn reply);

// One row of the command table: which verb, how many arguments it accepts, and which function handles it.
struct command {
    const char* verb;       // verb: PING, FREQ, etc.
    int min_args;           // fewest args after the vern
    int max_args;           // most args after the verb
    handler_fn handler;     // function called when the verb matches and the count is OK
};  


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

// FREQ <pin> <window_ms>: frequency and duty cycle of the signal on <pin> over the window
//   frequency_hz = (rising edges - 1) / (time from first to last rising edge)
//   duty_pct     = average high time / average period
//   edge_count   = rising edges in the window
// Fewer than 2 rising edges is a valid "no signal" result: frequency and duty are null.
static void cmd_freq(const struct args *a, reply_fn reply){

    char msg[REPLY_MAX];
    const char* name = a->argv[1];
    const struct pin_def* p = pins_find(name);
    uint32_t window_ms;
    struct capture_raw raw;
    struct reply_buf r;

    if (p == NULL){
        snprintf(msg, sizeof(msg), "pin %.16s is not in the pin map", name);
        reply_err(reply, "BADPIN", msg);
        return;
    }
    if (!pins_can_capture(p)){
        snprintf(msg, sizeof(msg), "pin %.16s has no timer_capture capability", name);
        reply_err(reply, "BADPIN", msg);
        return;
    }
    if (!pins_wired(p)){
        snprintf(msg, sizeof(msg), "pin %.16s is not wired (TBD in the pin map)", name);
        reply_err(reply, "BADPIN", msg);
        return;
    }
    if (!parse_u32(a->argv[2], 10000, &window_ms) || window_ms < 1){
        reply_err(reply, "BADARG", "window_ms must be 1-10000");
        return;
    }

    int rc = capture_measure(p->port, p->pin, window_ms, &raw);
    if (rc == CAPTURE_NO_TIMER){
        snprintf(msg, sizeof(msg), "no capture timer on P%c%u (pin %.16s)", p->port, (unsigned)p->pin, name);
        reply_err(reply, "BADPIN", msg);
        return;
    }
    if (rc != CAPTURE_OK){
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
// to boot. Later this also frees ARM slots.
static void cmd_reset(const struct args *a, reply_fn reply){

    char msg[REPLY_MAX];
    struct reply_buf r;
    const struct pin_def* p = pins_reset_line();
    (void) a;

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
static struct trace_raw trace_buf;            // ~1 KB: kept off the stack
static int64_t trace_us[TRACE_MAX_EDGES];     // edge times in us (= ms with 3 decimals)

static void cmd_trace(const struct args *a, reply_fn reply){

    char msg[REPLY_MAX];
    const char* name = a->argv[1];
    const struct pin_def* p = pins_find(name);
    uint32_t window_ms;
    struct reply_buf r;

    if (p == NULL){
        snprintf(msg, sizeof(msg), "pin %.16s is not in the pin map", name);
        reply_err(reply, "BADPIN", msg);
        return;
    }
    if (!pins_is_gpio(p)){
        snprintf(msg, sizeof(msg), "pin %.16s has no gpio capability", name);
        reply_err(reply, "BADPIN", msg);
        return;
    }
    if (!pins_wired(p)){
        snprintf(msg, sizeof(msg), "pin %.16s is not wired (TBD in the pin map)", name);
        reply_err(reply, "BADPIN", msg);
        return;
    }
    if (!parse_u32(a->argv[2], 10000, &window_ms) || window_ms < 1){
        reply_err(reply, "BADARG", "window_ms must be 1-10000");
        return;
    }

    int rc = trace_measure(p->port, p->pin, window_ms, &trace_buf);
    if (rc == TRACE_NO_PORT){
        snprintf(msg, sizeof(msg), "no GPIO port %c (pin %.16s)", p->port, name);
        reply_err(reply, "INTERNAL", msg);
        return;
    }
    if (rc != TRACE_OK || trace_buf.clock_hz == 0){
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

// DELAY <from_pin> <from_edge> <to_pin> <to_edge> <timeout_ms>   (edges: RISING|FALLING|ANY)
//   delay_ms      = time from the first from_edge on from_pin (the trigger) to the first
//                   to_edge on to_pin after it, in ms (us resolution); null if none came
//   to_edge_count = to_edges on to_pin from the trigger until timeout_ms after it
// The reply always takes the full timeout after the trigger. The trigger must come within
// timeout_ms of the request, otherwise ERR TIMEOUT: the rig failed to trigger. If from_pin
// is a pin the board drives, the board's own DRIVE is the trigger (that needs ARM, since
// DELAY blocks until it is done).
static void cmd_delay(const struct args *a, reply_fn reply){

    char msg[REPLY_MAX];
    const char* from_name = a->argv[1];
    const char* to_name = a->argv[3];
    const struct pin_def* from = pins_find(from_name);
    const struct pin_def* to = pins_find(to_name);
    uint8_t from_edge, to_edge;
    uint32_t timeout_ms;
    struct delay_raw raw;
    struct reply_buf r;

    if (!pin_usable(from, from_name, pins_is_gpio(from), "gpio", reply) ||
        !pin_usable(to, to_name, pins_can_capture(to), "timer_capture", reply)){
        return;
    }
    if ((from_edge = parse_edge(a->argv[2])) == 0){
        reply_err(reply, "BADARG", "from_edge must be RISING, FALLING or ANY");
        return;
    }
    if ((to_edge = parse_edge(a->argv[4])) == 0){
        reply_err(reply, "BADARG", "to_edge must be RISING, FALLING or ANY");
        return;
    }
    if (!parse_u32(a->argv[5], 10000, &timeout_ms) || timeout_ms < 1){
        reply_err(reply, "BADARG", "timeout_ms must be 1-10000");
        return;
    }
    // the STM32 has one edge interrupt line per pin number (PA3 and PB3 share line 3)
    if (from->pin == to->pin && from->port != to->port){
        snprintf(msg, sizeof(msg), "pins %.16s and %.16s share edge interrupt line %u",
                 from_name, to_name, (unsigned)from->pin);
        reply_err(reply, "BADARG", msg);
        return;
    }

    struct delay_pin f = {from->port, from->pin, from_edge, pins_can_drive(from)};
    struct delay_pin t = {to->port, to->pin, to_edge, pins_can_drive(to)};
    int rc = delay_measure(&f, &t, timeout_ms, &raw);

    if (rc == DELAY_NO_TRIGGER){
        uint32_t window_ms = timeout_ms > DELAY_TRIGGER_MIN_MS ? timeout_ms : DELAY_TRIGGER_MIN_MS;
        snprintf(msg, sizeof(msg), "no %s edge on %.16s within %u ms",
                 a->argv[2], from_name, (unsigned)window_ms);
        reply_err(reply, "TIMEOUT", msg);
        return;
    }
    if (rc == DELAY_NO_PORT){
        snprintf(msg, sizeof(msg), "no GPIO port for P%c%u or P%c%u",
                 from->port, (unsigned)from->pin, to->port, (unsigned)to->pin);
        reply_err(reply, "INTERNAL", msg);
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

// Command Table
// Need to add delay, uart, arm/collect here as they are implemented
static const struct command commands[] = {
    {"PING", 0, 0, cmd_ping},
    {"FREQ", 2, 2, cmd_freq},
    {"WAIT", 1, 1, cmd_wait},
    {"RESET", 0, 0, cmd_reset},
    {"TRACE", 2, 2, cmd_trace},
    {"DRIVE", 2, 5, cmd_drive},
    {"DELAY", 5, 5, cmd_delay},
};


// ------------------------------ dispatch -----------------------------------

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

// Handle one request line: split it find the verb in the commands, check number of args, and call the handler
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

    // parsing through the available commands (only have PING right now)
    for (size_t i = 0; i < sizeof(commands) / sizeof(commands[0]); i++){

        // the current command that is being processed
        const struct command *c = &commands[i];

        // comapres the strings to see if the verb and arg match
        if (strcmp(a.argv[0], c->verb) != 0){
            continue;
        }

        // number of args, not counting the verb itself
        int n = a.argc - 1;

        // wrong arg count: reply with what was expected
        if (n < c->min_args || n > c->max_args){
            if (c->min_args == c->max_args){
                snprintf(msg, sizeof(msg), "%s takes %d arguments, got %d", c->verb, c->min_args, n);
            }
            else {
                snprintf(msg, sizeof(msg), "%s takes %d-%d arguments, got %d", c->verb, c->min_args, c->max_args, n);
            }
            reply_err(reply, "BADCMD", msg);
            return;
        }

        // verb and arg count are valid: handler checks the arg
        c->handler(&a, reply);
        return;
    }

    // No row matches.
    snprintf(msg, sizeof(msg), "unknown verb %.32s", a.argv[0]);
    reply_err(reply, "BADCMD", msg);
}