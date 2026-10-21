# Lab 3: Hardware PWM (mock handout)

> Mock handout written for testing `grader make-plan`. It is not an official course
> document.

## Goal

Generate a **1 kHz** square wave with a **25 % duty cycle** on pin **D5** of your
Arduino Nano 33 BLE Sense.

## Requirements

1. The signal on D5 must have a frequency of 1 kHz and a duty cycle of 25 %.
2. The signal must start on its own after reset. No serial input or button press is
   needed.
3. You must use one of the nRF52840's **hardware timers / PWM peripherals**. Solutions
   that toggle the pin from `loop()` with `delay()` or `delayMicroseconds()`, or that use
   `analogWrite()`, will lose points at the TA review.

## Submission

Submit a single sketch folder containing your `.ino` file (and any `.cpp`/`.h` files it
uses). Comment the register values or constants you chose and explain how you computed
them.

## Hints

* The PWM output must be stable soon after boot; the grader starts measuring shortly
  after reset.
* Check your prescaler and counter-top values carefully: being off by a factor of two is
  the most common mistake.
