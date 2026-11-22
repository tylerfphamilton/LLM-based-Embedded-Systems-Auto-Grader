/*
 * Lab 5: answer ID?/SUM?/HEX? on Serial1
 *
 * ID: 000369852
 * SUM computed at runtime from the digits.
 * HEX printed with Serial's HEX formatter (upper case).
 */

const char myId[] = "000369852";
String inLine;

int computeSum() {
  int s = 0;
  for (const char *p = myId; *p; ++p) s += (*p - '0');
  return s;
}

void answer(const String &c) {
  if (c == "ID?")       Serial1.println(myId);
  else if (c == "SUM?") Serial1.println(computeSum());
  else if (c == "HEX?") Serial1.println(strtoul(myId, 0, 10), HEX);
  else                  Serial1.println("ERR");
}

void setup() {
  Serial1.begin(115200);
  inLine.reserve(16);
}

void loop() {
  while (Serial1.available()) {
    char c = Serial1.read();
    if (c == '\r') continue;          // ignore CR from CRLF endings
    if (c == '\n') {
      if (inLine.length()) answer(inLine);
      inLine = "";
    } else {
      inLine += c;
    }
  }
}
