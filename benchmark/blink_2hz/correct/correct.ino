void setup() {
  pinMode(LED_BUILTIN, OUTPUT);   // D13: the Nano's orange LED
}

void loop() {
  digitalWrite(LED_BUILTIN, HIGH);
  delay(250);
  digitalWrite(LED_BUILTIN, LOW);
  delay(250);
}