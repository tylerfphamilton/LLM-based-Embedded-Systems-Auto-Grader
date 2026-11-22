# `uart_id` benchmark (sketches still to be written)

Planned submissions for `plans/uart_id.json` (handout: `handouts/uart_id.md`). Each
folder `X/` needs `X/X.ino`. Use the ID from `params.yaml` for that submission; every ID is
made up and starts with `000`. Don't name the bug in the sketch (no "Planted bug" or
"Scenario:" comments: `test_scenario_sketch_links_exist` rejects them, and the LLM must not
read the answer).

| Submission | Faulty | Bug | Checks that should FAIL |
|---|---|---|---|
| `correct` | no | — | none |
| `correct_alt_style` | no | different parsing style (e.g. char-by-char state machine) | none |
| `copied_id` | yes | prints another student's ID: `correct`'s `000412387` (and its sum and hex) | `id_lf`, `sum`, `hex`, `id_crlf`, `id_again` text |
| `ascii_sum` | yes | sums the characters' ASCII codes, not the digit values (prints 461, not 29) | `sum.text` |
| `lf_only` | yes | only accepts `\n`; with `\r\n` the `\r` breaks the match (replies `ERR`) | `id_crlf.text` |
| `no_err` | yes | ignores unknown commands instead of replying `ERR` | `unknown.text` |
| `answers_once` | yes | stops replying after the first command | every text check after `id_lf` |
| `wrong_baud` | yes | `Serial1.begin(115200)` | every text check (it cannot decode 9600-baud commands; any reply is junk with framing errors) |
| `hex_lowercase` | yes | prints hex in lower case | `hex.text` (only if the ID's hex has a letter; `B6093` does) |
| `usb_serial` | yes | uses `Serial` instead of `Serial1` | every text check (nothing received) |

Notes for writing the sketches:

* The plan first sends one empty line (`\n`) and ignores what happens; the handout says to
  ignore empty lines.
* No start-up message: the rig only starts reading after the reset and a 1000 ms boot wait.
* `scenarios/uart_id/` simulates `correct`, `copied_id`, `ascii_sum` and `no_err` with the
  same IDs. Once a sketch exists, add `sketch: benchmark/uart_id/<name>` to its scenario so
  the feedback tests can read the code.

Once the sketches exist:

```powershell
grader batch --plan plans/uart_id.json --submissions benchmark/uart_id --rig serial --out out/uart_id_hw --feedback none
```
