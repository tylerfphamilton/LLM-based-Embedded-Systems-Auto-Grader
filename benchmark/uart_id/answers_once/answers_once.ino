// Lab 5 - serial "student ID" responder
//
// Serial1 @ 9600. setup() waits for a command line, strips the line
// ending with trim(), skips blank lines, and sends the matching reply.
//
// ID 000903317 -> digit sum 9+3+3+1+7 = 23, hex 903317 = DC895

const char ID[] = "000903317";

void sendReply(const String &cmd) {
  if (cmd == "ID?") {
    Serial1.println(ID);
  } else if (cmd == "SUM?") {
    Serial1.println(23);
  } else if (cmd == "HEX?") {
    Serial1.println("DC895");
  } else {
    Serial1.println("ERR");
  }
}

void setup() {
  Serial1.begin(9600);

  String cmd = "";
  // keep reading lines until we get a non-empty one
  while (cmd.length() == 0) {
    if (Serial1.available()) {
      cmd = Serial1.readStringUntil('\n');
      cmd.trim();
    }
  }
  sendReply(cmd);
}

void loop() {
}
