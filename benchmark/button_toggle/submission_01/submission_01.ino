// Lab 4 - debounced button toggle
// D2 = button to GND (INPUT_PULLUP, reads LOW when pressed)
// D13 = on-board LED
// Serial1 @ 9600 prints the LED state on every toggle

const int BUTTON_PIN = 2;
const int LED_PIN = 13;
const unsigned long DEBOUNCE_MS = 5;   // input must be stable for 5 ms

int lastRaw = HIGH;          // raw reading last time through loop()
int debounced = HIGH;        // accepted (debounced) button level
unsigned long lastEdgeMs = 0;
bool ledOn = false;

void setup() {
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);   // start with LED off
  Serial1.begin(9600);
}

void loop() {
  int raw = digitalRead(BUTTON_PIN);

  // any change restarts the debounce timer
  if (raw != lastRaw) {
    lastEdgeMs = millis();
    lastRaw = raw;
  }

  // accept the new level once it has been stable long enough
  if (millis() - lastEdgeMs >= DEBOUNCE_MS && raw != debounced) {
    debounced = raw;

    if (debounced == LOW) {   // button went down
      Serial1.println(ledOn ? "ON" : "OFF");
      ledOn = !ledOn;
      digitalWrite(LED_PIN, ledOn ? HIGH : LOW);
    }
  }
}
