// Button toggle with debounce
// pin 2: button (pull-up), pin 13: LED, Serial1 @ 9600

const int BTN_PIN = 2;
const int DEBOUNCE = 5;

int stable = HIGH;
int previous = HIGH;
unsigned long changedAt = 0;
bool on = false;

void setup() {
  pinMode(BTN_PIN, INPUT_PULLUP);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  Serial1.begin(9600);
}

void loop() {
  int now = digitalRead(BTN_PIN);
  if (now != previous) {
    changedAt = millis();
    previous = now;
  }
  if (millis() - changedAt > DEBOUNCE && now != stable) {
    stable = now;
    if (stable == HIGH) {   // one full click
      on = !on;
      digitalWrite(LED_BUILTIN, on ? HIGH : LOW);
      Serial1.println(on ? "ON" : "OFF");
    }
  }
}
