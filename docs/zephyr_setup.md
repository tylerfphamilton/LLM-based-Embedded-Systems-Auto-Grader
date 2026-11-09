# Zephyr setup (Windows)

Tested with Zephyr v4.4.0 and Zephyr SDK 1.0.1 on Windows 11 with PowerShell. On macOS
or Linux, follow the [Zephyr Getting Started Guide](https://docs.zephyrproject.org/latest/develop/getting_started/index.html)
for steps 1–5 and use the same Zephyr version.

The Zephyr workspace lives in your home folder, **outside this repo**. It is several GB
of code we didn't write and is never committed. This repo only holds `firmware/`. Building and flashing the firmware itself is in
[`firmware/README.md`](../firmware/README.md).

```
C:\Users\<you>\
├── zephyrproject\          ← Zephyr workspace + its own Python venv
└── dev\LLM-based-Embedded-Systems-Auto-Grader\
    ├── .venv\              ← grader venv
    └── firmware\           ← our firmware
```

## 1. Install the build tools

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

## 2. Create the Zephyr workspace

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

## 3. Install the ARM compiler

```powershell
cd ~\zephyrproject\zephyr
west sdk install --gnu-toolchains arm-zephyr-eabi
```

If it fails with "Zephyr SDK setup requires '7z'", 7-Zip is not on PATH: see step 1.
Delete the half-installed `C:\Users\<you>\zephyr-sdk-1.0.1` folder and run it again.

## 4. Install STM32CubeProgrammer

Download STM32CubeProgrammer (Windows 64) from st.com. Extract the zip, run the
installer, keep the default install location, and accept the ST-Link drivers.
`west flash` uses it.

## 5. Point west at Zephyr

```powershell
[Environment]::SetEnvironmentVariable("ZEPHYR_BASE", "$HOME\zephyrproject\zephyr", "User")
```

Open a new window afterwards. Without `ZEPHYR_BASE`, `west build` outside the
workspace fails with `unknown command "build"`.

## 6. Check the toolchain with hello_world

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

## Two terminals, two venvs

Both environments are called `.venv`, so the prompt looks the same. Keep one terminal
for each and don't switch:

| Terminal | Activate | Use for |
|---|---|---|
| zephyr | `~\zephyrproject\.venv\Scripts\Activate.ps1` | `west build`, `west flash` |
| grader | `.venv\Scripts\Activate.ps1` (repo root) | `rig_check.py`, `pytest`, `grader`, git |

`(Get-Command python).Source` shows which one is active.

## Troubleshooting

| Error | Fix |
|---|---|
| `west` is not recognized | The grader venv is active. Activate the Zephyr venv. |
| `unknown command "build"` | `ZEPHYR_BASE` is not set in this window (step 5). |
| `CMake is not installed` / `unable to find ... Ninja` | Tool not on PATH (step 1). Restart VS Code fully. |
| Tools still missing after fixing PATH in a window | Run `deactivate` before re-activating: activation restores the PATH saved when the venv was first activated. |
| `Aborting due to Kconfig warnings` | A misspelled `CONFIG_` option in `prj.conf`. Check the name in the Zephyr Kconfig search. |
| `could not open port` | Close miniterm or anything else using the COM port. |
| No output in miniterm | The board printed at boot before the port opened. Press RESET. |
