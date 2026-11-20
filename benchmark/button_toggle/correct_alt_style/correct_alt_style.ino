/*
 * Button toggles the LED, with software debounce.
 * D2 = button (active low), LED_BUILTIN = LED, Serial1 = status output.
 */

#define BTN 2

enum State { RELEASED, MAYBE_PRESSED, PRESSED, MAYBE_RELEASED };

State state = RELEASED;
unsigned long timerStart;
bool led = false;

void report() {
  if (led) {
    Serial1.print("ON\n");
  } else {
    Serial1.print("OFF\n");
  }
}

void setup() {
  pinMode(BTN, INPUT_PULLUP);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  Serial1.begin(9600);
}

void loop() {
  bool down = (digitalRead(BTN) == LOW);
  unsigned long now = millis();

  switch (state) {
    case RELEASED:
      if (down) { state = MAYBE_PRESSED; timerStart = now; }
      break;
    case MAYBE_PRESSED:
      if (!down) {
        state = RELEASED;
      } else if (now - timerStart >= 10) {
        state = PRESSED;
        led = !led;
        digitalWrite(LED_BUILTIN, led);
        report();
      }
      break;
    case PRESSED:
      if (!down) { state = MAYBE_RELEASED; timerStart = now; }
      break;
    case MAYBE_RELEASED:
      if (down) {
        state = PRESSED;
      } else if (now - timerStart >= 10) {
        state = RELEASED;
      }
      break;
  }
}
