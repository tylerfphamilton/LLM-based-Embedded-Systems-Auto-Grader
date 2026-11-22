/*
 * Lab 5 - "student ID" responder on Serial1 (9600 8N1)
 *
 * Commands are matched one character at a time with a small state
 * machine instead of buffering the whole line:
 *   - START: first char picks the candidate command (I, S or H)
 *   - MATCH: keep checking chars against that command's text
 *   - BAD:   line can no longer match anything, reply ERR at the end
 * '\r' and '\n' both end a line; a line with no characters is ignored,
 * so "\r\n" just looks like a line followed by an empty line.
 *
 * Answers were worked out by hand:
 *   ID  = 000527164
 *   SUM = 0+0+0+5+2+7+1+6+4 = 25
 *   HEX = 527164 decimal = 0x80B3C
 */

enum ParseState { START, MATCH, BAD };

const char *const COMMANDS[] = { "ID?", "SUM?", "HEX?" };
const char *const REPLIES[]  = { "000527164", "25", "80B3C" };
const int NUM_COMMANDS = 3;

ParseState state = START;
int candidate = -1;   // index into COMMANDS while in MATCH
int pos = 0;          // how many chars of the line we've seen

void endOfLine() {
  if (pos > 0) {      // empty lines get no reply
    if (state == MATCH && COMMANDS[candidate][pos] == '\0') {
      Serial1.print(REPLIES[candidate]);
      Serial1.print('\n');
    } else {
      Serial1.print("ERR\n");
    }
  }
  state = START;
  candidate = -1;
  pos = 0;
}

void feed(char c) {
  switch (state) {
    case START:
      state = BAD;
      for (int i = 0; i < NUM_COMMANDS; i++) {
        if (COMMANDS[i][0] == c) {
          candidate = i;
          state = MATCH;
          break;
        }
      }
      break;
    case MATCH:
      if (COMMANDS[candidate][pos] != c) {
        state = BAD;
      }
      break;
    case BAD:
      break;
  }
  pos++;
}

void setup() {
  Serial1.begin(9600);
}

void loop() {
  if (Serial1.available()) {
    char c = (char)Serial1.read();
    if (c == '\r' || c == '\n') {
      endOfLine();
    } else {
      feed(c);
    }
  }
}
