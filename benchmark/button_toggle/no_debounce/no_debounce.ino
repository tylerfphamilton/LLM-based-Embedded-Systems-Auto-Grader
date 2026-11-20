// Toggle the LED with an interrupt on the button pin

volatile bool ledState = false;
volatile bool changed = false;

void buttonPressed() {
  ledState = !ledState;
  digitalWrite(LED_BUILTIN, ledState);
  changed = true;
}

void setup() {
  pinMode(2, INPUT_PULLUP);
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  Serial1.begin(9600);
  attachInterrupt(digitalPinToInterrupt(2), buttonPressed, FALLING);  // button pulls D2 low
}

void loop() {
  if (changed) {
    changed = false;
    Serial1.println(ledState ? "ON" : "OFF");
  }
}
