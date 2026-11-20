// Debounced toggle: wait for the contacts to settle, then check again

bool ledOn = false;

void setup() {
  pinMode(2, INPUT_PULLUP);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  Serial1.begin(9600);
}

void loop() {
  if (digitalRead(2) == LOW) {
    delay(35);                      // let the bounce die out
    if (digitalRead(2) == LOW) {    // still pressed: real press
      ledOn = !ledOn;
      digitalWrite(LED_BUILTIN, ledOn ? HIGH : LOW);
      Serial1.println(ledOn ? "ON" : "OFF");
      while (digitalRead(2) == LOW) {
        // wait for release
      }
    }
  }
}
