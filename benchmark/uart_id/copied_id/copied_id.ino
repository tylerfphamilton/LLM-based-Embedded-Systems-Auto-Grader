// Lab 5 - serial ID responder
// Serial1 9600 baud. Reads a line, strips the line ending, and answers
// ID? / SUM? / HEX?, anything else gets ERR.

#define MY_ID "000412387"

String buffer = "";

// add up the digits of the ID string
int sumDigits(const char *s) {
  int total = 0;
  while (*s) {
    total += *s - '0';
    s++;
  }
  return total;
}

void reply(String cmd) {
  if (cmd == "ID?") {
    Serial1.println(MY_ID);
  } else if (cmd == "SUM?") {
    Serial1.println(sumDigits(MY_ID));
  } else if (cmd == "HEX?") {
    unsigned long n = atol(MY_ID);       // leading zeros don't matter here
    Serial1.println(n, HEX);
  } else {
    Serial1.println("ERR");
  }
}

void setup() {
  Serial1.begin(9600);
}

void loop() {
  while (Serial1.available()) {
    char c = Serial1.read();
    if (c == '\n') {
      buffer.trim();                     // removes the '\r' if the line was CRLF
      if (buffer.length() > 0) {
        reply(buffer);
      }
      buffer = "";
    } else {
      buffer += c;
    }
  }
}
