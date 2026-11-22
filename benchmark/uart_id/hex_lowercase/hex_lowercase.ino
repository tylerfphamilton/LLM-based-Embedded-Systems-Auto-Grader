// Lab 5 - student ID responder (Serial1, 9600 baud)
//
// All three answers are built once as Strings in setup(), then each
// command just prints the matching String.
//   ID  : "000745619"
//   SUM : digits added together
//   HEX : String(value, HEX) gives the hex digits with no leading zeros

const char ID_TEXT[] = "000745619";

String idReply, sumReply, hexReply;
String pending;

void setup() {
  Serial1.begin(9600);

  unsigned long idNum = 0;
  int digits = 0;
  for (int i = 0; ID_TEXT[i]; i++) {
    int d = ID_TEXT[i] - '0';
    digits += d;
    idNum = idNum * 10 + d;
  }

  idReply  = String(ID_TEXT);
  sumReply = String(digits);
  hexReply = String(idNum, HEX);
}

void loop() {
  while (Serial1.available()) {
    char c = Serial1.read();
    if (c == '\n') {
      pending.trim();                 // drop '\r' and stray spaces
      if (pending.length() > 0) {
        if (pending == "ID?")        Serial1.println(idReply);
        else if (pending == "SUM?")  Serial1.println(sumReply);
        else if (pending == "HEX?")  Serial1.println(hexReply);
        else                         Serial1.println("ERR");
      }
      pending = "";
    } else {
      pending += c;
    }
  }
}
