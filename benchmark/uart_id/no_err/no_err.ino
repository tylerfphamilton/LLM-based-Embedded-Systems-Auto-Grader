/*
  Lab 5 -- ID responder

  Listens on Serial1 (9600 8N1). Characters are collected until a
  newline; carriage returns are skipped so CRLF and LF both work.

  My ID: 000276548
    digit sum = 2+7+6+5+4+8 = 32
    hex       = 276548 -> 0x43844
*/

#define BAUD 9600

static const char kId[]  = "000276548";
static const int  kSum   = 32;
static const unsigned long kIdNum = 276548UL;

static char rx[20];
static int  rxCount = 0;

static void processLine(const char *s) {
  if (!strcmp(s, "ID?")) {
    Serial1.println(kId);
  } else if (!strcmp(s, "SUM?")) {
    Serial1.println(kSum);
  } else if (!strcmp(s, "HEX?")) {
    Serial1.println(kIdNum, HEX);
  }
}

void setup() {
  Serial1.begin(BAUD);
}

void loop() {
  while (Serial1.available()) {
    int b = Serial1.read();
    if (b == '\r') continue;

    if (b == '\n') {
      rx[rxCount] = 0;
      if (rxCount) processLine(rx);   // blank lines are ignored
      rxCount = 0;
    } else if (rxCount < (int)sizeof(rx) - 1) {
      rx[rxCount++] = (char)b;
    }
  }
}
