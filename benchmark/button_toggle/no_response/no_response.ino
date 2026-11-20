// button toggle lab

const int buttonPin = 3;
const int ledPin = 13;
const unsigned long debounceDelay = 5;

int buttonState = HIGH;
int lastButtonState = HIGH;
unsigned long lastDebounceTime = 0;
int ledState = LOW;

void setup() {
  pinMode(buttonPin, INPUT_PULLUP);
  pinMode(ledPin, OUTPUT);
  digitalWrite(ledPin, ledState);
  Serial1.begin(9600);
}

void loop() {
  int reading = digitalRead(buttonPin);

  if (reading != lastButtonState) {
    lastDebounceTime = millis();
  }

  if ((millis() - lastDebounceTime) > debounceDelay) {
    if (reading != buttonState) {
      buttonState = reading;
      if (buttonState == LOW) {
        ledState = !ledState;
        digitalWrite(ledPin, ledState);
        if (ledState == HIGH) {
          Serial1.println("ON");
        } else {
          Serial1.println("OFF");
        }
      }
    }
  }

  lastButtonState = reading;
}
