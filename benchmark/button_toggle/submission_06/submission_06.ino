// Lab 4: debounced LED toggle
//
// Approach: after a toggle, ignore the button for a lockout period so
// the contact bounce can't cause extra toggles. Uses millis() so there
// is no blocking delay.
//
// D2  - button to GND, INPUT_PULLUP (LOW while pressed)
// D13 - LED
// Serial1 9600 - prints new state

#define BUTTON_PIN  2
#define LED_PIN     LED_BUILTIN
#define LOCKOUT_MS  200

bool led = false;
unsigned long lastToggle = 0;

void setup() {
  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  Serial1.begin(9600);
}

void loop() {
  // pressed, and we're outside the lockout window
  if (digitalRead(BUTTON_PIN) == LOW && millis() - lastToggle >= LOCKOUT_MS) {
    led = !led;
    digitalWrite(LED_PIN, led ? HIGH : LOW);
    Serial1.println(led ? "ON" : "OFF");
    lastToggle = millis();
  }
}
