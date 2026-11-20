// Lab 4 - button toggles LED, prints state on Serial1

#define BUTTON 2
#define LED LED_BUILTIN
#define DEBOUNCE_TIME 5   // ms

bool lightOn = false;
bool wasPressed = false;
unsigned long pressStart = 0;
bool counted = false;

void setup() {
  pinMode(BUTTON, INPUT_PULLUP);
  pinMode(LED, OUTPUT);
  digitalWrite(LED, LOW);
  Serial1.begin(115200);
}

void loop() {
  bool pressed = digitalRead(BUTTON) == LOW;

  if (pressed && !wasPressed) {
    pressStart = millis();   // contact just closed (or bounced)
    counted = false;
  }
  if (!pressed) {
    counted = false;
  }

  if (pressed && !counted && millis() - pressStart >= DEBOUNCE_TIME) {
    counted = true;
    lightOn = !lightOn;
    digitalWrite(LED, lightOn);
    Serial1.println(lightOn ? "ON" : "OFF");
  }

  wasPressed = pressed;
}
