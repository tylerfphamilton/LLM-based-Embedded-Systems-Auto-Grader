/*
 * Lab 4: Button toggle
 *
 * Button: D2, internal pull-up, active low
 * LED:    LED_BUILTIN (D13)
 * Output: Serial1, 9600 baud
 *
 * Debounce: the button has to read the same value for DEBOUNCE_TIME ms
 * in a row before we treat it as a real change. Uses millis() so the
 * loop never blocks.
 */

#define BUTTON        2
#define DEBOUNCE_TIME 8

bool ledState = false;
int  stableLevel = HIGH;
int  prevLevel = HIGH;
unsigned long changeTime = 0;

// send the current state out the UART
void sendState() {
  if (ledState) {
    Serial1.print("ON");
  } else {
    Serial1.print("OFF");
  }
}

void setup() {
  pinMode(BUTTON, INPUT_PULLUP);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  Serial1.begin(9600);
}

void loop() {
  int level = digitalRead(BUTTON);

  if (level != prevLevel) {
    changeTime = millis();      // bounce or real edge, restart timing
  }
  prevLevel = level;

  if ((millis() - changeTime) >= DEBOUNCE_TIME) {
    if (level != stableLevel) {
      stableLevel = level;
      if (stableLevel == LOW) {          // pressed
        ledState = !ledState;
        digitalWrite(LED_BUILTIN, ledState);
        sendState();
      }
    }
  }
}
