/*
 * Lab 5 - Serial student ID responder
 *
 * Serial1, 9600 8N1.
 * ID?  -> my ID with leading zeros
 * SUM? -> sum of the digits of my ID
 * HEX? -> ID in upper-case hex
 * other -> ERR
 */

const char *studentId = "000194726";

unsigned long idValue;   // numeric value of the ID, for the hex reply
int idDigitSum;          // computed once in setup()

char cmdBuf[24];
int cmdLen = 0;

void setup() {
  Serial1.begin(9600);

  // precompute the answers so replies are instant
  idValue = strtoul(studentId, nullptr, 10);
  idDigitSum = 0;
  for (size_t i = 0; i < strlen(studentId); i++) {
    idDigitSum += studentId[i];
  }
}

void runCommand() {
  if (strcmp(cmdBuf, "ID?") == 0) {
    Serial1.println(studentId);
  } else if (strcmp(cmdBuf, "SUM?") == 0) {
    Serial1.println(idDigitSum);
  } else if (strcmp(cmdBuf, "HEX?") == 0) {
    Serial1.println(idValue, HEX);
  } else {
    Serial1.println("ERR");
  }
}

void loop() {
  while (Serial1.available()) {
    char ch = Serial1.read();

    if (ch == '\n' || ch == '\r') {
      if (cmdLen > 0) {          // skip blank lines and the 2nd half of CRLF
        cmdBuf[cmdLen] = '\0';
        runCommand();
        cmdLen = 0;
      }
    } else if (cmdLen < (int)sizeof(cmdBuf) - 1) {
      cmdBuf[cmdLen++] = ch;
    }
  }
}
