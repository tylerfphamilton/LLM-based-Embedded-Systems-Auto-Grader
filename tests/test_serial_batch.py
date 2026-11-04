"""Batches of real sketch folders: discovery, labels, the serial batch flow, --flash-only and
the flasher's wait for the USB port. All with fakes: no hardware, no network, no sleeping."""

from __future__ import annotations

import csv
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from grader.batch import (
    DEAD_RIG,
    discover_submissions,
    flash_only_batch,
    format_flash_table,
    load_labels,
    run_serial_batch,
)
from grader.cli import app
from grader.fake_rig import FakeDevice, GroundTruth, Scenario
from grader.flasher import ArduinoCliFlasher, Flasher, FlashResult, Submission
from grader.pinmap import pinmap_hash
from grader.plan import load_plan
from grader.transport import ARDUINO_VID, FakeTransport

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "plans" / "pwm_1khz.json"
runner = CliRunner()


def _sketches(folder: Path, *names: str) -> Path:
    for n in names:
        (folder / n).mkdir(parents=True)
        (folder / n / f"{n}.ino").write_text("void setup() {}\nvoid loop() {}\n", encoding="utf-8")
    return folder


def _device(pinmap, **extra) -> FakeDevice:
    """A measuring board that answers PING/RESET/WAIT and a correct 1 kHz / 25 % FREQ."""
    scenario = Scenario.model_validate(
        {
            "submission": "rig",
            "responses": [
                {
                    "match": {"cmd": "FREQ", "pin": "D5"},
                    "reply": {"frequency_hz": 1000.0, "duty_pct": 25.0, "edge_count": 100},
                }
            ],
            **extra,
        }
    )
    return FakeDevice(scenario, pinmap_hash=pinmap_hash(pinmap))


class RecordingFlasher(Flasher):
    kind = "test"

    def __init__(self, raise_for: str | None = None, compile_fails: str | None = None):
        self.flashed: list[str] = []
        self.raise_for, self.compile_fails = raise_for, compile_fails

    def flash(self, submission: Submission) -> FlashResult:
        self.flashed.append(submission.id)
        if submission.id == self.raise_for:
            raise RuntimeError("flasher blew up")
        if submission.id == self.compile_fails:
            return FlashResult(False, "compile", "error: x was not declared", student_fault=True)
        return FlashResult(True, "done", f"uploaded {submission.id}")


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ------------------------------------------------------------------- discovery, labels


def test_discover_submissions(tmp_path: Path, capsys) -> None:
    _sketches(tmp_path, "zeta", "alpha")
    (tmp_path / "notes").mkdir()
    (tmp_path / "mismatch").mkdir()
    (tmp_path / "mismatch" / "other.ino").write_text("", encoding="utf-8")
    (tmp_path / "labels.yaml").write_text("{}", encoding="utf-8")
    subs = discover_submissions(tmp_path)
    assert [s.id for s in subs] == ["alpha", "zeta"]
    assert subs[0].sketch_dir == tmp_path / "alpha"
    err = capsys.readouterr().err
    assert "skipping" in err and "notes" in err and "mismatch" in err


def test_load_labels(tmp_path: Path, capsys) -> None:
    _sketches(tmp_path, "good", "bad")
    assert load_labels(tmp_path) == {}  # no file: all unlabelled
    (tmp_path / "labels.yaml").write_text(
        "good: { faulty: false }\nbad: { faulty: true, fault: wrong_pin }\n"
        "ghost: { faulty: true }\n",
        encoding="utf-8",
    )
    labels = load_labels(tmp_path)
    assert labels["bad"] == GroundTruth(faulty=True, fault="wrong_pin")
    assert labels["good"].faulty is False
    assert "'ghost' has no matching submission folder" in capsys.readouterr().err


def test_benchmark_folder_is_complete() -> None:
    folder = ROOT / "benchmark" / "pwm_1khz"
    ids = [s.id for s in discover_submissions(folder)]
    assert sorted(load_labels(folder)) == ids and len(ids) == 6


# ------------------------------------------------------------------------- serial batch


def _serial(tmp_path: Path, pinmap, rig_profile, device: FakeDevice, flasher: Flasher, **labels):
    folder = _sketches(tmp_path / "subs", "a", "b", "c")
    return run_serial_batch(
        load_plan(PLAN),
        discover_submissions(folder),
        {k: GroundTruth.model_validate(v) for k, v in labels.items()},
        transport=FakeTransport(device),
        flasher=flasher,
        pinmap=pinmap,
        rig_profile=rig_profile,
        out_dir=tmp_path / "out",
    )


def test_serial_batch_flashes_in_order_and_uses_labels(tmp_path, pinmap, rig_profile) -> None:
    flasher = RecordingFlasher()
    rows, m, stopped = _serial(
        tmp_path, pinmap, rig_profile, _device(pinmap), flasher,
        a={"faulty": False}, b={"faulty": True, "fault": "wrong_duty"},
    )  # fmt: skip
    assert stopped is None and flasher.flashed == ["a", "b", "c"]
    assert [r.passed for r in rows] == [2, 2, 2]
    # The rig says every sketch is correct, so the faulty 'b' is a missed bug.
    assert (m.faulty, m.correct, m.unlabelled, m.detected, m.false_failures) == (1, 1, 1, 0, 0)
    table = _read_csv(tmp_path / "out" / "summary.csv")
    assert [r["submission"] for r in table] == ["a", "b", "c"]
    assert [r["ground_truth_faulty"] for r in table] == ["false", "true", ""]
    assert all(r["elapsed_s"] for r in table)
    assert (tmp_path / "out" / "c" / "report.json").exists()


def test_serial_batch_survives_an_exception(tmp_path, pinmap, rig_profile, capsys) -> None:
    flasher = RecordingFlasher(raise_for="b")
    rows, _, stopped = _serial(tmp_path, pinmap, rig_profile, _device(pinmap), flasher)
    assert stopped is None and flasher.flashed == ["a", "b", "c"]
    assert rows[1].error == "RuntimeError: flasher blew up"
    assert (rows[1].errors, rows[1].passed) == (2, 0)
    assert rows[2].passed == 2
    assert "b: grading raised RuntimeError: flasher blew up" in capsys.readouterr().err
    assert len(_read_csv(tmp_path / "out" / "summary.csv")) == 3


def test_dead_rig_stops_the_batch(tmp_path, pinmap, rig_profile, capsys) -> None:
    # The board answers the first PING ('a'), then goes silent: 'b' fails its handshake.
    device = _device(pinmap, fail_command={"cmd": "PING", "after": 1, "silent": True})
    flasher = RecordingFlasher()
    rows, _, stopped = _serial(tmp_path, pinmap, rig_profile, device, flasher)
    assert flasher.flashed == ["a"]
    assert [r.submission for r in rows] == ["a", "b"] and rows[1].errors == 2
    assert stopped is not None and DEAD_RIG in stopped and DEAD_RIG in capsys.readouterr().err
    assert [r["submission"] for r in _read_csv(tmp_path / "out" / "summary.csv")] == ["a", "b"]


def test_ctrl_c_writes_partial_summary(tmp_path, pinmap, rig_profile) -> None:
    class Interrupting(RecordingFlasher):
        def flash(self, submission):
            if submission.id == "b":
                raise KeyboardInterrupt
            return super().flash(submission)

    with pytest.raises(KeyboardInterrupt):
        _serial(tmp_path, pinmap, rig_profile, _device(pinmap), Interrupting())
    assert [r["submission"] for r in _read_csv(tmp_path / "out" / "summary.csv")] == ["a"]


# ---------------------------------------------------------------------------- flash-only


def test_flash_only_batch(tmp_path: Path) -> None:
    subs = discover_submissions(_sketches(tmp_path / "subs", "good", "broken"))
    labels = {"good": GroundTruth(faulty=False)}
    out = tmp_path / "out"
    rows = flash_only_batch(
        subs, labels, flasher=RecordingFlasher(compile_fails="broken"), out_dir=out
    )
    table = _read_csv(out / "flash_summary.csv")
    assert [(r["submission"], r["label"], r["flash_ok"], r["stage"], r["student_fault"])
            for r in table] == [
        ("broken", "unlabelled", "false", "compile", "true"),
        ("good", "correct", "true", "done", "false"),
    ]  # fmt: skip
    assert all(r["elapsed_s"] for r in table)
    assert "was not declared" in (out / "broken" / "flash.log").read_text(encoding="utf-8")
    assert "1 ok / 1 failed" in format_flash_table(rows)


# ----------------------------------------------------------------------------------- CLI


def _cli(*args: str):
    return runner.invoke(app, ["batch", "--plan", str(PLAN), *args])


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["--rig", "serial", "--scenarios", "scenarios/pwm"], "not --scenarios"),
        (["--rig", "serial"], "--rig serial needs --submissions"),
        (["--scenarios", "scenarios/pwm", "--flash-only"], "--flash-only needs --rig serial"),
        (["--submissions", "benchmark/pwm_1khz"], "--submissions needs --rig serial"),
        ([], "--rig fake needs --scenarios"),
        (["--rig", "serial", "--submissions", "nope"], "nope is not a directory"),
        (["--scenarios", "nope"], "nope is not a directory"),
        (
            [
                "--rig",
                "serial",
                "--submissions",
                "benchmark/pwm_1khz",
                "--flash-only",
                "--feedback",
                "llm",
            ],
            "cannot use --feedback llm",
        ),
    ],
)
def test_cli_rejects_bad_combinations(args, message, monkeypatch) -> None:
    monkeypatch.chdir(ROOT)
    res = _cli(*args)
    assert res.exit_code == 2 and message in res.output


def test_cli_serial_batch_opens_one_transport(tmp_path, pinmap, monkeypatch) -> None:
    import grader.flasher
    import grader.transport

    opened: list[str | None] = []
    flasher = RecordingFlasher()

    def fake_serial(port=None):
        opened.append(port)
        return FakeTransport(_device(pinmap))

    monkeypatch.setattr(grader.transport, "SerialTransport", fake_serial)
    monkeypatch.setattr(grader.flasher, "ArduinoCliFlasher", lambda **kw: flasher)
    monkeypatch.chdir(ROOT)
    res = _cli(
        "--rig", "serial", "--submissions", "benchmark/pwm_1khz", "--port", "COM9",
        "--out", str(tmp_path),
    )  # fmt: skip
    assert res.exit_code == 0, res.output
    assert opened == ["COM9"]
    assert flasher.flashed == sorted(flasher.flashed) and len(flasher.flashed) == 6
    assert "Bug detection rate : 0.0%  (0/3" in res.output  # the fake rig passes everything


def test_cli_flash_only_creates_no_transport(tmp_path, monkeypatch) -> None:
    import grader.flasher
    import grader.transport

    def no_serial(*a, **kw):
        raise AssertionError("--flash-only must not open the measuring board")

    monkeypatch.setattr(grader.transport, "SerialTransport", no_serial)
    monkeypatch.setattr(grader.flasher, "ArduinoCliFlasher", lambda **kw: RecordingFlasher())
    monkeypatch.chdir(ROOT)
    res = _cli(
        "--rig", "serial", "--submissions", "benchmark/pwm_1khz", "--flash-only",
        "--out", str(tmp_path),
    )  # fmt: skip
    assert res.exit_code == 0, res.output
    assert "6 ok / 0 failed" in res.output
    assert len(_read_csv(tmp_path / "flash_summary.csv")) == 6


# ------------------------------------------------------------------- flasher port wait


class FakeTime:
    def __init__(self) -> None:
        self.t = 0.0
        self.sleeps: list[float] = []

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s

    def monotonic(self) -> float:
        return self.t


def _flasher(lister, clock: FakeTime) -> ArduinoCliFlasher:
    def ok_run(args, **kw):
        return SimpleNamespace(returncode=0, stdout=f"{args[1]} ok\n", stderr="")

    return ArduinoCliFlasher(
        port="COM5", run=ok_run, port_lister=lister, sleep=clock.sleep, monotonic=clock.monotonic
    )


def test_flasher_waits_for_port_then_settles(tmp_path: Path) -> None:
    polls = []

    def lister():
        polls.append(1)
        return [SimpleNamespace(device="COM5", vid=ARDUINO_VID)] if len(polls) > 3 else []

    clock = FakeTime()
    res = _flasher(lister, clock).flash(Submission("s", tmp_path))
    assert res.ok and res.stage == "done"
    assert len(polls) == 4 and clock.sleeps == [0.2, 0.2, 0.2, 1.0]  # three polls, then settle


def test_flasher_port_never_returns(tmp_path: Path) -> None:
    clock = FakeTime()
    res = _flasher(lambda: [], clock).flash(Submission("s", tmp_path))
    assert not res.ok and res.stage == "upload" and not res.student_fault
    assert "did not come back within 10.0 s" in res.log
    assert clock.t == pytest.approx(10.0, abs=0.2) and 1.0 not in clock.sleeps
