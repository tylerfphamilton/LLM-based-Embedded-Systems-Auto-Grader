# Lab 5: Serial "student ID" responder (mock handout)

> Mock handout written for testing `grader make-plan` with per-student values. It is not
> an official course document.

## Goal

Write a sketch that answers simple text commands over a serial port, using values worked
out from **your own university ID**. Every student's correct answers are different.

## Hardware

* **Serial1** (pins D0/D1), not the USB `Serial` port, at **9600 baud**, 8N1.
* Nothing else is connected.

## Commands

The grader sends one command per line. A line may end with `\n` or with `\r\n`, and your
sketch must accept both (the `\r` is part of the line ending, not of the command). Ignore
empty lines.

| Command | Reply (one line) |
|---|---|
| `ID?` | your 9-digit university ID, e.g. `905123456` |
| `SUM?` | the sum of your ID's digits, e.g. `35` |
| `HEX?` | your ID as an upper-case hexadecimal number without leading zeros, e.g. `35F31680` |
| anything else | `ERR` |

End every reply with `\r\n` (`Serial1.println`) or `\n`.

## Requirements

1. Use your own university ID. Keep the leading zeros in the `ID?` reply.
2. Reply promptly to every command, for as long as the board is powered: the sketch must
   keep answering, not just the first time.
3. Print nothing except the replies (no start-up message, no debug output on Serial1).
4. Comment your code.

## Submission

Submit your sketch folder.
