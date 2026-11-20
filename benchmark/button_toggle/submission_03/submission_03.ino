// Lab 4 - Button toggles LED
//
// Wiring: push button between D2 and GND, using INPUT_PULLUP so the
// pin is HIGH when released and LOW when pressed.
// The Nano 33 BLE's on-board LEDs are active low, so writing LOW turns
// the LED on and HIGH turns it off.

const int BTN = 2;
const int LED = LED_BUILTIN;

#define LED_ON   LOW
#define LED_OFF  HIGH

const unsigned long DEBOUNCE = 5;   // ms

bool isOn = false;            // logical LED state
int lastRead = HIGH;
int confirmed = HIGH;
unsigned long lastChange = 0;

void setLed(bool on) {
  digitalWrite(LED, on ? LED_ON : LED_OFF);
}

void setup() {
  pinMode(BTN, INPUT_PULLUP);
  pinMode(LED, OUTPUT);
  setLed(false);              // LED off at reset
  Serial1.begin(9600);
}

void loop() {
  int r = digitalRead(BTN);

  if (r != lastRead) {
    lastChange = millis();
    lastRead = r;
  }

  if (millis() - lastChange >= DEBOUNCE && r != confirmed) {
    confirmed = r;
    if (confirmed == LOW) {
      isOn = !isOn;
      setLed(isOn);
      Serial1.println(isOn ? "ON" : "OFF");
    }
  }
}
