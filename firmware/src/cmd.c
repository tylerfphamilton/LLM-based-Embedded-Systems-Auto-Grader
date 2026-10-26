#include "cmd.h"

#include <stdio.h>
#include <string.h>

#include "version.h"

// most tokens a request can have (including the verb)
#define MAX_ARGS 16

// Size of the buffer for formatted error replies
#define REPLY_MAX 1100

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

// license and version check (host sends it on connect after a T.O. to make sure the board is answering)
static void cmd_ping(const struct args *a, reply_fn reply){
    
    (void) a;
    reply("OK fw=\"" FW_VERSION "\" protocol=\"" PROTOCOL_VERSION "\"");
}

// Command Table
// Need to add reset, wait, drive, freq, ... here as they are implemented
static const struct command commands[] = {
    {"PING", 0, 0, cmd_ping},
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
        reply("ERR BADCMD too many arguments");
        return;
    }

    // check to see if there are blank lines or a line of only spaces
    if (a.argc == 0){
        reply("ERR BADCMD empty request");
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
                snprintf(msg, sizeof(msg), "ERR BADCMD %s takes %d arguments, got %d", c->verb, c->min_args, n);
            }
            else {
                snprintf(msg, sizeof(msg), "ERR BADCMD %s takes %d-%d arguments, got %d", c->verb, c->min_args, c->max_args, n);
            }
            reply(msg);
            return;
        }

        // verb and arg count are valid: handler checks the arg
        c->handler(&a, reply);
        return;
    }

    // No ros matches.
    snprintf(msg, sizeof(msg), "ERR BADCMD unknown verb %.32s", a.argv[0]);
    reply(msg);
}


