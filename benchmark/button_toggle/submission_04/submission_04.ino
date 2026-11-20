// button toggle w/ software debounce
// D2 button (pullup, LOW = pressed), D13 LED, Serial1 9600

int buttonPin = 2;
int ledPin = 13;

int ledState = LOW;
int buttonState = HIGH;        // debounced button
int lastReading = HIGH;        // previous raw reading
unsigned long lastBounce = 0;  // time of the last raw change
unsigned long debounceMs = 6;

void setup() {
  pinMode(buttonPin, INPUT_PULLUP);
  pinMode(ledPin, OUTPUT);
  digitalWrite(ledPin, ledState);
  Serial1.begin(9600);
}

void loop() {
  int reading = digitalRead(buttonPin);

  // raw input changed -> remember when
  if (reading != lastReading)
    lastReading = reading;
    lastBounce = millis();

  // only act after the input has been steady for debounceMs
  if ((millis() - lastBounce) >= debounceMs) {
    if (reading != buttonState) {
      buttonState = reading;

      if (buttonState == LOW) {
        ledState = !ledState;
        digitalWrite(ledPin, ledState);
        Serial1.println(ledState == HIGH ? "ON" : "OFF");
      }
    }
  }
}
