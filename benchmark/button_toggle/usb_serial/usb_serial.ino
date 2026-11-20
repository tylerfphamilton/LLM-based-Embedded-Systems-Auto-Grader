// Button toggles LED and prints the new state

const int button = 2;
const int led = LED_BUILTIN;

int lastStable = HIGH;
int lastRaw = HIGH;
unsigned long rawChangedMs = 0;
bool isOn = false;

void setup() {
  pinMode(button, INPUT_PULLUP);
  pinMode(led, OUTPUT);
  digitalWrite(led, LOW);
  Serial.begin(9600);
}

void loop() {
  int raw = digitalRead(button);
  if (raw != lastRaw) {
    rawChangedMs = millis();
    lastRaw = raw;
  }
  if (millis() - rawChangedMs >= 5 && raw != lastStable) {
    lastStable = raw;
    if (raw == LOW) {
      isOn = !isOn;
      digitalWrite(led, isOn);
      Serial.println(isOn ? "ON" : "OFF");
    }
  }
}
