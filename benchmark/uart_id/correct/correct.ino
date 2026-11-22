// Lab 5: serial student ID responder
// Serial1 @ 9600 8N1. Reads one command per line and replies with values
// computed from my ID. Accepts both "\n" and "\r\n" line endings.

const char STUDENT_ID[] = "000412387";   // kept as a string so the leading zeros stay

char line[32];        // current command being received
uint8_t len = 0;      // number of chars in line[]

// sum of the decimal digits of the ID
int digitSum() {
  int sum = 0;
  for (int i = 0; STUDENT_ID[i] != '\0'; i++) {
    sum += STUDENT_ID[i] - '0';
  }
  return sum;
}

// handle one complete command
void handleCommand(const char *cmd) {
  if (strcmp(cmd, "ID?") == 0) {
    Serial1.println(STUDENT_ID);
  } else if (strcmp(cmd, "SUM?") == 0) {
    Serial1.println(digitSum());
  } else if (strcmp(cmd, "HEX?") == 0) {
    unsigned long value = strtoul(STUDENT_ID, NULL, 10);
    Serial1.println(value, HEX);   // Print uses upper-case hex digits, no leading zeros
  } else {
    Serial1.println("ERR");
  }
}

void setup() {
  Serial1.begin(9600);
}

void loop() {
  while (Serial1.available() > 0) {
    char c = Serial1.read();

    if (c == '\r') {
      continue;                  // part of a CRLF ending, drop it
    }
    if (c == '\n') {
      line[len] = '\0';
      if (len > 0) {             // ignore empty lines
        handleCommand(line);
      }
      len = 0;
      continue;
    }
    if (len < sizeof(line) - 1) {
      line[len++] = c;           // overly long lines are truncated
    }
  }
}
