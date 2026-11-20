// Lab 4 - toggle LED with a debounced button
//
// D2: button to ground. Configure as input and write HIGH to turn on
//     the internal pull-up resistor, so it reads LOW when pressed.
// D13: LED
// Serial1: 9600 baud status messages

#define BTN_PIN      2
#define LED_PIN      13
#define DEBOUNCE_MS  5

bool lit = false;
int lastSample = HIGH;
int btnState = HIGH;
unsigned long sampleChangedAt = 0;

void setup() {
  pinMode(BTN_PIN, INPUT);
  digitalWrite(BTN_PIN, HIGH);     // pull-up on

  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Serial1.begin(9600);
}

void loop() {
  int sample = digitalRead(BTN_PIN);

  if (sample != lastSample) {
    sampleChangedAt = millis();
    lastSample = sample;
  }

  if (millis() - sampleChangedAt >= DEBOUNCE_MS && sample != btnState) {
    btnState = sample;
    if (btnState == LOW) {
      lit = !lit;
      digitalWrite(LED_PIN, lit ? HIGH : LOW);
      Serial1.println(lit ? "ON" : "OFF");
    }
  }
}
