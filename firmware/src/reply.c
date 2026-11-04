// reply builder: see reply.h. Numbers are formatted by hand from integers (no printf, no floats),
// so the output is the same with any libc

#include "reply.h"

#include <string.h>

// longest number this file formats: sign + 20 digits + '.' + 18 decimals, plus slack
#define NUM_MAX 48

// longest decimals reply_fixed accepts (10^18 still fits in a uint64_t with room to spare)
#define MAX_DECIMALS 18

static const char TRUNCATED[] = " truncated=1";

// ------------------------------- helpers -----------------------------------

// append n bytes, or mark the reply as overflowed if they don't fit
static void append(struct reply_buf *r, const char *s, size_t n){

    if (r->overflow){
        return;
    }
    if (r->len + n > PROTO_LINE_MAX){
        r->overflow = true;
        return;
    }
    memcpy(&r->text[r->len], s, n);
    r->len += n;
    r->text[r->len] = '\0';
}

static void append_str(struct reply_buf *r, const char *s){
    append(r, s, strlen(s));
}

// " key="
static void append_key(struct reply_buf *r, const char *key){
    append(r, " ", 1);
    append_str(r, key);
    append(r, "=", 1);
}

// unsigned decimal digits of v into out, returns the length
static size_t fmt_u64(char *out, uint64_t v){

    char rev[20];
    size_t n = 0;

    // digits come out least significant first
    do {
        rev[n++] = (char)('0' + v % 10);
        v /= 10;
    } while (v != 0);

    for (size_t i = 0; i < n; i++){
        out[i] = rev[n - 1 - i];
    }
    return n;
}

// magnitude of v as unsigned, works for INT64_MIN too
static uint64_t magnitude(int64_t v){
    return v < 0 ? (uint64_t)0 - (uint64_t)v : (uint64_t)v;
}

static size_t fmt_int(char *out, int64_t v){

    size_t n = 0;
    if (v < 0){
        out[n++] = '-';
    }
    return n + fmt_u64(&out[n], magnitude(v));
}

// scaled / 10^decimals as "[-]whole.frac", trailing zeros dropped but at least one decimal kept
static size_t fmt_fixed(char *out, int64_t scaled, int decimals){

    uint64_t pow = 1;
    uint64_t mag = magnitude(scaled);
    size_t n = 0;

    if (decimals < 0){
        decimals = 0;
    }
    if (decimals > MAX_DECIMALS){
        decimals = MAX_DECIMALS;
    }
    for (int i = 0; i < decimals; i++){
        pow *= 10;
    }

    if (scaled < 0){
        out[n++] = '-';
    }
    n += fmt_u64(&out[n], mag / pow);
    out[n++] = '.';

    // fraction, zero padded to 'decimals' digits
    uint64_t frac = mag % pow;
    for (int i = decimals - 1; i >= 0; i--){
        out[n + (size_t)i] = (char)('0' + frac % 10);
        frac /= 10;
    }
    n += (size_t)decimals;

    // drop trailing zeros, but keep one digit after the '.'
    while (out[n - 1] == '0' && out[n - 2] != '.'){
        n--;
    }
    if (out[n - 1] == '.'){
        out[n++] = '0';
    }
    return n;
}

// ------------------------------- builders ----------------------------------

void reply_begin(struct reply_buf *r){

    r->len = 0;
    r->overflow = false;
    r->truncated = false;
    r->text[0] = '\0';
    append(r, "OK", 2);
}

void reply_int(struct reply_buf *r, const char *key, int64_t v){

    char num[NUM_MAX];
    append_key(r, key);
    append(r, num, fmt_int(num, v));
}

void reply_fixed(struct reply_buf *r, const char *key, int64_t scaled, int decimals){

    char num[NUM_MAX];
    append_key(r, key);
    append(r, num, fmt_fixed(num, scaled, decimals));
}

void reply_null(struct reply_buf *r, const char *key){

    append_key(r, key);
    append(r, "null", 4);
}

void reply_str(struct reply_buf *r, const char *key, const uint8_t *bytes, size_t n){

    static const char hex[] = "0123456789ABCDEF";

    append_key(r, key);
    append(r, "\"", 1);
    for (size_t i = 0; i < n; i++){
        uint8_t b = bytes[i];

        // safe bytes go as they are, everything else as %XX
        if (b >= 0x21 && b <= 0x7E && b != '%' && b != '"' && b != ','){
            append(r, (const char *)&b, 1);
        }
        else {
            char esc[3] = {'%', hex[b >> 4], hex[b & 0x0F]};
            append(r, esc, 3);
        }
    }
    append(r, "\"", 1);
}

void reply_list_fixed(struct reply_buf *r, const char *key, const int64_t *scaled, size_t n, int decimals){

    char num[NUM_MAX];
    size_t full = 0;

    append_key(r, key);
    append(r, "[", 1);
    if (r->overflow){
        return;
    }

    // first pass: does the whole list (plus the closing ']') fit?
    for (size_t i = 0; i < n; i++){
        full += fmt_fixed(num, scaled[i], decimals) + (i > 0 ? 1 : 0);
    }
    bool cut = r->len + full + 1 > PROTO_LINE_MAX;

    // room to keep at the end: ']' and, if cutting, " truncated=1" (only once per line)
    size_t reserve = 1 + (cut && !r->truncated ? sizeof(TRUNCATED) - 1 : 0);

    for (size_t i = 0; i < n; i++){
        size_t len = fmt_fixed(num, scaled[i], decimals);
        size_t comma = i > 0 ? 1 : 0;

        if (r->len + comma + len + reserve > PROTO_LINE_MAX){
            break;
        }
        append(r, ",", comma);
        append(r, num, len);
    }
    append(r, "]", 1);

    if (cut && !r->truncated){
        append_str(r, TRUNCATED);
        r->truncated = true;
    }
}

void reply_send(struct reply_buf *r, reply_fn reply){

    if (r->overflow){
        reply("ERR INTERNAL reply too long");
        return;
    }
    reply(r->text);
}

void reply_err(reply_fn reply, const char *code, const char *msg){

    char line[PROTO_LINE_MAX + 1];
    size_t n = 0;
    size_t len;

    // "ERR " + code, cut to the line limit
    memcpy(line, "ERR ", 4);
    n = 4;
    len = strlen(code);
    if (len > PROTO_LINE_MAX - n){
        len = PROTO_LINE_MAX - n;
    }
    memcpy(&line[n], code, len);
    n += len;

    // " " + msg, if there is a message and room for it
    if (msg != NULL && msg[0] != '\0' && n + 1 < PROTO_LINE_MAX){
        line[n++] = ' ';
        len = strlen(msg);
        if (len > PROTO_LINE_MAX - n){
            len = PROTO_LINE_MAX - n;
        }
        memcpy(&line[n], msg, len);
        n += len;
    }
    line[n] = '\0';
    reply(line);
}
