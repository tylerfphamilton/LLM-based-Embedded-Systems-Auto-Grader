# Lab 4: Debounced button toggle (mock handout)

> Mock handout written for testing `grader make-plan`. It is not an official course
> document.

## Goal

Use a push button to toggle an LED, and report each change over a serial port.

## Hardware

* A push button between pin **D2** and GND. There is no external resistor, so use the
  internal pull-up (`INPUT_PULLUP`). The button reads LOW while pressed.
* The on-board LED on pin **D13**.
* **Serial1** (pins D0/D1), not the USB `Serial` port, at **9600 baud**.

## Requirements

1. The LED is **off** after reset.
2. Each press of the button toggles the LED: the first press turns it on, the next one
   turns it off, and so on.
3. The LED must react **quickly**: a user should not notice any delay.
4. Real buttons bounce. One press must toggle the LED exactly **once**, no matter how
   much the contacts bounce.
5. On every toggle, print `ON` or `OFF` (the new state) on its own line on Serial1.
6. Implement debouncing in software, without blocking `delay()` calls.
7. Comment your code.

## Submission

Submit your sketch folder.
