// Lab 5: serial ID responder
// Answers ID?, SUM? and HEX? at 9600 baud; unknown commands get ERR.
// Line endings: '\r' is dropped, '\n' ends the command.

const char STUDENT_ID[] = "000580274";

char cmd[16];
byte n = 0;

int idSum() {
  int t = 0;
  for (byte i = 0; STUDENT_ID[i]; i++) t += STUDENT_ID[i] - '0';
  return t;
}

void handle() {
  if (strcmp(cmd, "ID?") == 0)        Serial.println(STUDENT_ID);
  else if (strcmp(cmd, "SUM?") == 0)  Serial.println(idSum());
  else if (strcmp(cmd, "HEX?") == 0)  Serial.println(strtoul(STUDENT_ID, NULL, 10), HEX);
  else                                Serial.println("ERR");
}

void setup() {
  Serial.begin(9600);
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      cmd[n] = '\0';
      if (n > 0) handle();
      n = 0;
    } else if (n < sizeof(cmd) - 1) {
      cmd[n++] = c;
    }
  }
}
