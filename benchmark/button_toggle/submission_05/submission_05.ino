/*
  Lab 4 - Debounced Toggle

  Reads the button on D2 (internal pull-up, so pressed = LOW) and
  toggles the built-in LED once per press. Each new state is sent on
  Serial1 at 9600 baud.

  I timestamp with micros() instead of millis() because millis() only
  has 1 ms resolution, so a debounce window of a few ms would have up
  to 1 ms of jitter.
*/

const uint8_t  kButton = 2;
const uint8_t  kLed = LED_BUILTIN;
const uint32_t kDebounce = 5;      // debounce window

bool     ledOn = false;
uint8_t  rawPrev = HIGH;
uint8_t  stable = HIGH;
uint32_t tChange = 0;

void setup() {
  pinMode(kButton, INPUT_PULLUP);
  pinMode(kLed, OUTPUT);
  digitalWrite(kLed, LOW);
  Serial1.begin(9600);
}

void loop() {
  uint8_t raw = digitalRead(kButton);
  uint32_t now = micros();

  // restart the window whenever the raw input moves
  if (raw != rawPrev) {
    rawPrev = raw;
    tChange = now;
  }

  // input has settled
  if (now - tChange >= kDebounce && raw != stable) {
    stable = raw;
    if (stable == LOW) {
      ledOn = !ledOn;
      digitalWrite(kLed, ledOn);
      Serial1.println(ledOn ? "ON" : "OFF");
    }
  }
}
