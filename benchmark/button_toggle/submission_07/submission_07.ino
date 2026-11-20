/*
 * Lab 4 - button toggle
 *
 * Toggle on the falling edge of D2 (button press). Bounce is handled by
 * ignoring any further edges for HOLDOFF_MS after an accepted press.
 * This responds instantly on the first edge, so there is no added latency.
 *
 * Pins: D2 button (INPUT_PULLUP), D13 LED. Serial1 at 9600 baud.
 */

const int buttonPin = 2;
const int ledPin    = 13;
const unsigned long HOLDOFF_MS = 30;

int  prev = HIGH;             // reading from the previous loop
bool ledOn = false;
unsigned long acceptedAt = 0; // time of the last accepted press

void setup() {
  pinMode(buttonPin, INPUT_PULLUP);
  pinMode(ledPin, OUTPUT);
  digitalWrite(ledPin, LOW);
  Serial1.begin(9600);
}

void loop() {
  int cur = digitalRead(buttonPin);

  // HIGH -> LOW transition = button pressed
  if (prev == HIGH && cur == LOW) {
    if (millis() - acceptedAt > HOLDOFF_MS) {
      ledOn = !ledOn;
      digitalWrite(ledPin, ledOn ? HIGH : LOW);
      Serial1.println(ledOn ? "ON" : "OFF");
      acceptedAt = millis();
    }
  }

  prev = cur;
}
