/*
 * Lab 4 - Debounced button toggle
 *
 * Structure: read + debounce the input, update the toggle state, then
 * drive the outputs (LED and serial) from the current state at the end
 * of every loop so they always match.
 *
 * D2 = button (INPUT_PULLUP, active low), D13 = LED, Serial1 = 9600 baud
 */

const int PIN_BUTTON = 2;
const int LED_PIN    = LED_BUILTIN;
const unsigned long DEBOUNCE_MS = 5;

bool ledOn = false;
int rawLast = HIGH;
int debouncedLast = HIGH;
unsigned long rawChangeMs = 0;

void setup() {
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  Serial1.begin(9600);
}

void loop() {
  // --- input ---
  int raw = digitalRead(PIN_BUTTON);
  if (raw != rawLast) {
    rawChangeMs = millis();
    rawLast = raw;
  }

  // --- debounce + toggle on press ---
  if (millis() - rawChangeMs >= DEBOUNCE_MS && raw != debouncedLast) {
    debouncedLast = raw;
    if (raw == LOW) {
      ledOn = !ledOn;
    }
  }

  // --- outputs ---
  digitalWrite(LED_PIN, ledOn ? HIGH : LOW);
  Serial1.println(ledOn ? "ON" : "OFF");
}
