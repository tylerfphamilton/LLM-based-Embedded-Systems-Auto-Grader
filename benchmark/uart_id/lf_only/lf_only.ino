// Lab 5: student ID over serial
//
// Serial1 at 9600 baud. Each command is read with readStringUntil('\n'),
// which returns the text before the newline (the '\n' itself is not
// included), so the string can be compared directly.
//
// ID  = 000851093
// SUM = 8+5+1+0+9+3 = 26
// HEX = 851093 = 0xCFC95

const String ID_STR  = "000851093";
const String SUM_STR = "26";
const String HEX_STR = "CFC95";

void setup() {
  Serial1.begin(9600);
}

void loop() {
  if (Serial1.available() > 0) {
    String cmd = Serial1.readStringUntil('\n');

    if (cmd.length() == 0) {
      return;                       // empty line, nothing to do
    }

    if (cmd == "ID?") {
      Serial1.println(ID_STR);
    } else if (cmd == "SUM?") {
      Serial1.println(SUM_STR);
    } else if (cmd == "HEX?") {
      Serial1.println(HEX_STR);
    } else {
      Serial1.println("ERR");
    }
  }
}
