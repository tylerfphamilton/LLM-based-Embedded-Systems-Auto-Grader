# AI Grader for Embedded Systems Assignments: host software

UCLA M202A project (Sean Hashem, Tyler Hamilton). This repo is the **host-side backbone**
of an automatic grader for Arduino assignments:

* **Student board:** Arduino Nano 33 BLE Sense running the student's sketch.
* **Measuring board:** STM32 Nucleo-L476RG wired pin-to-pin to the student board. It runs
  fixed firmware that takes text commands (`FREQ D5 100`) and replies with numbers.
* **Host (this repo):** flashes the sketch, runs a **test plan** against the measuring
  board, turns measurements into verdicts, and writes reports.
* **LLM (optional):** drafts test plans from handouts and explains failed checks (see
  [LLM features](#llm-features)). It never decides a verdict.

The hardware hasn't arrived yet, so everything runs against a **FakeRig** that speaks the
same text protocol as the planned firmware.

## Quickstart

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate     Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"          # add ,serial for real hardware: pip install -e ".[dev,serial]"
pytest                           # ~260 tests, ~1.5 s, no hardware or network
ruff check . && ruff format --check .

grader validate-plan plans/pwm_1khz.json
grader run   --plan plans/pwm_1khz.json --rig fake --scenario scenarios/pwm/wrong_prescaler.yaml --out out/
grader batch --plan plans/pwm_1khz.json      --scenarios scenarios/pwm/    --out out/pwm
grader batch --plan plans/button_toggle.json --scenarios scenarios/button/ --out out/button
grader export-schema             # regenerate schemas/plan.schema.json after changing plan.py
```

To run on real hardware, set up Zephyr and flash the measuring board first: see
[Hardware setup (Zephyr)](#hardware-setup-zephyr).

`run` writes `out/<submission>/report.json` (everything, including the full command log)
and `out/<submission>/report.md` (for the student). `batch` also writes `summary.csv` and
prints the benchmark metrics:

```
submission                   truth            PASS FAIL BORD  ERR
-----------------------------------------------------------------
pwm_borderline               correct             1    0    1    0
pwm_correct                  correct             2    0    0    0
pwm_wrong_prescaler          wrong_prescaler     1    1    0    0
...
Bug detection rate : 100.0%  (3/3 faulty submissions with >= 1 FAIL)
False failure rate : 0.0%  (0/4 correct submissions with >= 1 FAIL)
```

## Architecture

A **plan** (JSON, `src/grader/plan.py`) is an ordered list of stimulus, wait and measure
steps. Each measure step lists expectations such as `frequency_hz approx 1000 ±2%`. After
schema checks and semantic checks against the **pin map** (`validate.py`), the **runner**
turns each step into a protocol `Command` (`protocol.py`), sends its text line over a
**Transport** (`FakeTransport` → `FakeDevice`, or `SerialTransport` → STM32), and parses
the reply line back into a measurement. The **comparator** (`compare.py`) turns
expectation + measurement + the rig's known error (`config/rig_profile.yaml`) into
`PASS`/`FAIL`/`BORDERLINE`/`ERROR`. This is a pure function, so verdicts are
deterministic. Rig faults (ERR replies, timeouts, garbled lines) always give `ERROR`,
never `FAIL`; a measured "no signal" is a real result and can `FAIL`. The **report**
module renders JSON and Markdown. Nothing in the code is specific to an assignment;
switching to hardware means swapping the transport and flasher. See `docs/DESIGN.md`,
`docs/protocol.md` (draft wire protocol for the firmware author) and `docs/decisions.md`.

```
src/grader/   plan, pinmap, validate, protocol, transport, fake_rig, rig_profile,
              compare, runner, report, flasher, feedback, batch, clock, cli,
              llm, planner, prompts/*.md
config/       pinmap.yaml (STM32 pins are PLACEHOLDERS), rig_profile.yaml (estimates),
              llm.yaml (model is a PLACEHOLDER)
plans/        one JSON per assignment (+ optional <name>.meta.yaml provenance, drafts/)
schemas/      plan.schema.json (generated)
scenarios/    <assignment>/*.yaml simulated submissions for the FakeRig
handouts/     mock handouts for make-plan     benchmark/  placeholder student sketches
tests/        pytest; tests/fixtures/bad_plans/ = plans that must be rejected
```

## Adding an assignment (no Python changes)

Walkthrough using the third example, `blink_2hz` ("blink the LED on D13 at 2 Hz").

**1. Write the plan**: `plans/blink_2hz.json`. The file name must equal `assignment`.

```json
{
  "schema_version": "0.1",
  "assignment": "blink_2hz",
  "description": "Blink the on-board LED (D13) at 2 Hz: 250 ms on, 250 ms off.",
  "setup": { "reset": true, "boot_wait_ms": 500 },
  "steps": [
    {
      "op": "measure", "id": "blink",
      "requirement": "LED on D13 toggles every 250 ms (8 edges in 2 s)",
      "primitive": "logic_trace", "pin": "D13", "window_ms": 2000,
      "expect": [ { "field": "edge_count", "op": "in_range", "low": 7, "high": 9 } ]
    }
  ],
  "not_graded": [],
  "assumptions": ["±1 edge allowed because the 2 s window starts at an arbitrary phase"]
}
```

**2. Validate it.** Errors are reported all at once, one sentence each (the LLM will get
these to repair its plans):

```bash
grader validate-plan plans/blink_2hz.json
# plans/blink_2hz.json: OK (1 steps, 1 measurements)
```

If you used a pin that isn't wired, or a field that `logic_trace` doesn't return:

```
  - step 'blink': pin D7 is not in the pin map.
  - step 'blink' expectation #1: field 'frequency_hz' is not returned by primitive 'logic_trace' (valid: edge_count, final_level, edges_ms).
```

**3. Write scenarios**: one YAML per simulated submission in `scenarios/blink/`. Each
gives the canned reply the measuring board would send, the ground truth (for metrics),
and the verdicts you expect (for the tests):

```yaml
# scenarios/blink/too_fast.yaml
submission: blink_too_fast
assignment: blink_2hz
description: delay(125) instead of delay(250), so the LED blinks at 4 Hz.
ground_truth: { faulty: true, fault: too_fast }
responses:
  - match: { cmd: TRACE, pin: D13 }          # matched against the parsed wire command
    reply: { edge_count: 16, final_level: 1, edges_ms: [] }
expected_verdicts:
  blink.edge_count: FAIL                     # check id = <step id>.<field>
```

Other scenario features: `replies:` (a list consumed in order for repeated commands),
`noise: {seed, fields: {frequency_hz: {pct: 0.05}}}`, `fail_command:` (make a command
reply `ERR …` or stay silent to simulate rig faults), and `debug_lines: true`.

**4. Run it.**

```bash
grader batch --plan plans/blink_2hz.json --scenarios scenarios/blink/ --out out/blink
pytest   # test_end_to_end.py picks up every scenarios/*/*.yaml automatically
```

That's all: `blink_2hz` was added to this repo with exactly these four data files and no
code changes.

## LLM features

Optional. They need the `llm` extra and an Anthropic API key. Without them everything
else works as before, and the default `pytest` run makes no network calls.

```bash
pip install -e ".[dev,llm]"
export ANTHROPIC_API_KEY=sk-ant-...          # PowerShell: $env:ANTHROPIC_API_KEY = "sk-ant-..."
# then edit config/llm.yaml: set `model` to a current Claude model ID. Leave
# force_tool: false unless that model accepts forced tool use (docs/decisions.md D37)
```

**Draft a plan from a handout.** Check the request first; `--dry-run` needs no key and
makes no API call:

```bash
grader make-plan --handout handouts/pwm_1khz.md --name pwm_1khz --dry-run
grader make-plan --handout handouts/pwm_1khz.md --name pwm_1khz
```

The LLM output is checked by the same schema + validator as a hand-written plan. Errors
are sent back to the model (up to 3 attempts). The result is
`plans/drafts/pwm_1khz.draft.json` plus `plans/pwm_1khz.meta.yaml` (provenance: handout
hash, model, prompt version, tokens) and `plans/drafts/pwm_1khz.log.json` (every raw
response).

**Make → review → approve.** A draft is never used directly. Read it, fix it, copy it to
`plans/<name>.json`, and approve that exact file:

```bash
grader approve-plan plans/pwm_1khz.json --by "Sean"
```

`run`/`batch` warn (and record `plan_warnings` in `report.json`) if a plan has a meta
file that isn't `approved`, or if the file changed after approval. Hand-written plans
without a meta file run as before. `approve-plan` creates a `source: hand` meta file for
them.

**Explain failures.** One API call per submission that has at least one FAIL:

```bash
grader batch --plan plans/pwm_1khz.json --scenarios scenarios/pwm/ --out out/pwm --feedback llm
```

The explanation appears in `report.md` under "What to fix". `report.json` gets an `llm`
section (model, prompt version, tokens, latency, warnings, error), and the raw exchange is
saved to `out/<submission>/llm_feedback.json`. The student's code is sent as untrusted
data; scenarios link to it with `sketch:`. Items that cite the wrong check or a value that
wasn't measured are dropped. If the call fails, the report simply has no feedback: the
verdicts are identical to `--feedback none` (the default).

Live smoke tests (cost money): `pytest -m live` with the key set and a real model in
`config/llm.yaml`.

## Hardware setup (Zephyr)

Tested with Zephyr v4.4.0 and Zephyr SDK 1.0.1 on Windows 11 with PowerShell. On macOS
or Linux, follow the [Zephyr Getting Started Guide](https://docs.zephyrproject.org/latest/develop/getting_started/index.html)
for steps 1–5 and use the same Zephyr version.

The Zephyr workspace lives in your home folder, **outside this repo**. It is several GB
of code we didn't write and is never committed. This repo only holds `firmware/`.

```
C:\Users\<you>\
├── zephyrproject\          ← Zephyr workspace + its own Python venv
└── dev\LLM-based-Embedded-Systems-Auto-Grader\
    ├── .venv\              ← grader venv
    └── firmware\           ← our firmware
```

### 1. Install the build tools

```powershell
winget install Kitware.CMake Ninja-build.Ninja oss-winget.gperf Python.Python.3.12 Git.Git oss-winget.dtc 7zip.7zip
```

Then **close every terminal and VS Code completely** and open a new PowerShell window.
Programs only see PATH changes after they restart. Check:

```powershell
cmake --version; ninja --version; dtc --version; gperf --version; 7z | Select-Object -First 2
```

If any tool is "not recognized", add its folder to your user PATH, then open a new window:

```powershell
$found = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages" -Recurse -Include ninja.exe, dtc.exe, gperf.exe
$need = @("C:\Program Files\CMake\bin", "C:\Program Files\7-Zip") + ($found | ForEach-Object { $_.DirectoryName } | Sort-Object -Unique)
$user = [Environment]::GetEnvironmentVariable("Path", "User")
foreach ($d in $need) { if (($user -split ';') -notcontains $d) { $user = $user.TrimEnd(';') + ";" + $d; "added $d" } }
[Environment]::SetEnvironmentVariable("Path", $user, "User")
```

### 2. Create the Zephyr workspace

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned   # once; lets venv activation scripts run
cd ~
py -3.12 -m venv zephyrproject\.venv
zephyrproject\.venv\Scripts\Activate.ps1
pip install west
west init -m https://github.com/zephyrproject-rtos/zephyr --mr v4.4.0 zephyrproject
cd zephyrproject
west update cmsis_6 hal_stm32
cmd /c zephyr\scripts\utils\west-packages-pip-install.cmd
west zephyr-export
```

`west update cmsis_6 hal_stm32` fetches only the two modules the Nucleo-L476RG needs.
Plain `west update` fetches every module (several GB) and also works.

### 3. Install the ARM compiler

```powershell
cd ~\zephyrproject\zephyr
west sdk install --gnu-toolchains arm-zephyr-eabi
```

If it fails with "Zephyr SDK setup requires '7z'", 7-Zip is not on PATH: see step 1.
Delete the half-installed `C:\Users\<you>\zephyr-sdk-1.0.1` folder and run it again.

### 4. Install STM32CubeProgrammer

Download STM32CubeProgrammer (Windows 64) from st.com. Extract the zip, run the
installer, keep the default install location, and accept the ST-Link drivers.
`west flash` uses it.

### 5. Point west at Zephyr

```powershell
[Environment]::SetEnvironmentVariable("ZEPHYR_BASE", "$HOME\zephyrproject\zephyr", "User")
```

Open a new window afterwards. Without `ZEPHYR_BASE`, `west build` outside the
workspace fails with `unknown command "build"`.

### 6. Check the toolchain with hello_world

```powershell
~\zephyrproject\.venv\Scripts\Activate.ps1
cd ~\zephyrproject\zephyr
west build -p always -b nucleo_l476rg samples\hello_world
west flash
python -m serial.tools.list_ports -v                  # find the ST-Link's COM port
python -m serial.tools.miniterm COM7 115200           # use your port
```

Press the Nucleo's black RESET button. You should see
`Hello World! nucleo_l476rg/stm32l476xx`. Exit miniterm with `Ctrl+]`.

### Two terminals, two venvs

Both environments are called `.venv`, so the prompt looks the same. Keep one terminal
for each and don't switch:

| Terminal | Activate | Use for |
|---|---|---|
| zephyr | `~\zephyrproject\.venv\Scripts\Activate.ps1` | `west build`, `west flash` |
| grader | `.venv\Scripts\Activate.ps1` (repo root) | `rig_check.py`, `pytest`, `grader`, git |

`(Get-Command python).Source` shows which one is active.

### Troubleshooting

| Error | Fix |
|---|---|
| `west` is not recognized | The grader venv is active. Activate the Zephyr venv. |
| `unknown command "build"` | `ZEPHYR_BASE` is not set in this window (step 5). |
| `CMake is not installed` / `unable to find ... Ninja` | Tool not on PATH (step 1). Restart VS Code fully. |
| Tools still missing after fixing PATH in a window | Run `deactivate` before re-activating: activation restores the PATH saved when the venv was first activated. |
| `Aborting due to Kconfig warnings` | A misspelled `CONFIG_` option in `prj.conf`. Check the name in the Zephyr Kconfig search. |
| `could not open port` | Close miniterm or anything else using the COM port. |
| No output in miniterm | The board printed at boot before the port opened. Press RESET. |

## Status and what is not here

* `SerialTransport` and `ArduinoCliFlasher` are written but **untested on hardware**;
  `--rig serial` warns about this.
* STM32 pin assignments in `config/pinmap.yaml` and the rig error figures in
  `config/rig_profile.yaml` are placeholders.
* The LLM layer has only been tested with a fake client: no API key was available, so
  the plan schema as a tool `input_schema` and the prompts are unverified (D38).
* Not in scope here: the STM32 firmware, web UI, queues, databases, parallel rigs, other
  LLM providers.
