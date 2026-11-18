const unsigned long HALF_PERIOD_MS = 125;

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
  digitalWrite(LED_BUILTIN, HIGH);
  delay(HALF_PERIOD_MS);
  digitalWrite(LED_BUILTIN, LOW);
  delay(HALF_PERIOD_MS);
}
