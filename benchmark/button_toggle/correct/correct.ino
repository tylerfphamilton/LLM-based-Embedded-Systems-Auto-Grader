// Lab 4: debounced button toggle
// Button on D2 to GND (internal pull-up, LOW when pressed), LED on D13,
// state printed on Serial1 at 9600 baud.

const int BUTTON_PIN = 2;
const int LED_PIN = LED_BUILTIN;
const unsigned long DEBOUNCE_MS = 4;  // reading must be stable this long

int lastReading = HIGH;   // raw reading from the previous loop
int buttonState = HIGH;   // debounced state
unsigned long lastChangeMs = 0;
bool ledOn = false;

void setup() {
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  Serial1.begin(9600);
}

void loop() {
  int reading = digitalRead(BUTTON_PIN);
  if (reading != lastReading) {
    lastChangeMs = millis();  // still bouncing, restart the timer
    lastReading = reading;
  }

  if (millis() - lastChangeMs >= DEBOUNCE_MS && reading != buttonState) {
    buttonState = reading;
    if (buttonState == LOW) {  // new press
      ledOn = !ledOn;
      digitalWrite(LED_PIN, ledOn ? HIGH : LOW);
      Serial1.println(ledOn ? "ON" : "OFF");
    }
  }
}
