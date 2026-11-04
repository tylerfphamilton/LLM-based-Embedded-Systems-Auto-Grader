#include "cmd.h"

#include <stdio.h>
#include <string.h>

#include "capture.h"
#include "pins.h"
#include "reply.h"
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

// Command Table
// Need to add reset, wait, drive, ... here as they are implemented
static const struct command commands[] = {
    {"PING", 0, 0, cmd_ping},
    {"FREQ", 2, 2, cmd_freq},
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