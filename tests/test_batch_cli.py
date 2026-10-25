from __future__ import annotations

import csv
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from grader.batch import BatchRow, compute_metrics, run_batch
from grader.cli import app
from grader.plan import load_plan
from grader.report import md_escape

ROOT = Path(__file__).resolve().parent.parent


def row(name: str, faulty: bool | None, failed: int, errors: int = 0, borderline: int = 0):
    return BatchRow(name, faulty, None, 1, failed, borderline, errors, None)


def test_compute_metrics() -> None:
    m = compute_metrics(
        [
            row("a", True, 1),
            row("b", True, 0, errors=2),  # missed bug (rig error, not a FAIL)
            row("c", False, 0),
            row("d", False, 1),  # false failure
            row("e", False, 0, borderline=1),
            row("f", None, 3),  # unlabelled: excluded from rates
        ]
    )
    assert (m.detected, m.faulty, m.detection_rate) == (1, 2, 0.5)
    assert (m.false_failures, m.correct) == (1, 3)
    assert m.false_failure_rate == pytest.approx(1 / 3)
    assert (m.error_checks, m.borderline_checks, m.unlabelled) == (2, 1, 1)


def test_rates_undefined_without_labels() -> None:
    m = compute_metrics([row("x", None, 0)])
    assert m.detection_rate is None and m.false_failure_rate is None


@pytest.mark.parametrize(
    ("assignment", "faulty", "correct", "errors", "borderline"),
    [("pwm_1khz", 3, 4, 2, 1), ("button_toggle", 4, 3, 8, 0)],
)
def test_example_batches(
    assignment, faulty, correct, errors, borderline, pinmap, rig_profile, tmp_path
) -> None:
    folder = {"pwm_1khz": "pwm", "button_toggle": "button"}[assignment]
    rows, m = run_batch(
        load_plan(ROOT / "plans" / f"{assignment}.json"),
        (ROOT / "scenarios" / folder).glob("*.yaml"),
        pinmap=pinmap,
        rig_profile=rig_profile,
        out_dir=tmp_path,
    )
    assert (m.faulty, m.correct) == (faulty, correct)
    assert m.detection_rate == 1.0 and m.false_failure_rate == 0.0
    assert (m.error_checks, m.borderline_checks) == (errors, borderline)
    with (tmp_path / "summary.csv").open(encoding="utf-8") as fh:
        table = list(csv.DictReader(fh))
    assert len(table) == len(rows) and {r["assignment"] for r in table} == {assignment}
    for r in rows:
        assert (tmp_path / r.submission / "report.md").exists()
        assert (tmp_path / r.submission / "report.json").exists()


def test_md_escape() -> None:
    assert md_escape(r"^\s*ON\s*$ | x_y") == r"^\\s\*ON\\s\*$ \| x\_y"


# ---------------------------------------------------------------------------------- CLI

runner = CliRunner()


def invoke(*args: str):
    return runner.invoke(app, list(args), catch_exceptions=False)


def test_cli_export_schema(tmp_path: Path) -> None:
    out = tmp_path / "s.json"
    assert invoke("export-schema", "--out", str(out), "--check").exit_code == 1
    assert invoke("export-schema", "--out", str(out)).exit_code == 0
    assert invoke("export-schema", "--out", str(out), "--check").exit_code == 0


def test_cli_validate_plan(monkeypatch) -> None:
    monkeypatch.chdir(ROOT)
    ok = invoke("validate-plan", "plans/pwm_1khz.json")
    assert ok.exit_code == 0 and "OK" in ok.output
    bad = invoke("validate-plan", "tests/fixtures/bad_plans/field_not_valid.json")
    assert bad.exit_code == 1 and "is not returned by primitive" in bad.output


def test_cli_run_and_batch(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(ROOT)
    res = invoke(
        "run", "--plan", "plans/pwm_1khz.json", "--rig", "fake",
        "--scenario", "scenarios/pwm/wrong_prescaler.yaml", "--out", str(tmp_path),
    )  # fmt: skip
    assert res.exit_code == 0 and "1 FAIL" in res.output
    assert (tmp_path / "pwm_wrong_prescaler" / "report.md").exists()

    res = invoke(
        "batch", "--plan", "plans/button_toggle.json", "--scenarios", "scenarios/button",
        "--out", str(tmp_path),
    )  # fmt: skip
    assert res.exit_code == 0
    assert "Bug detection rate : 100.0%" in res.output
    assert "False failure rate : 0.0%" in res.output


def test_cli_rejects_scenario_for_other_assignment(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(ROOT)
    shutil.copy(ROOT / "scenarios/button/correct.yaml", tmp_path / "x.yaml")
    res = runner.invoke(
        app, ["batch", "--plan", "plans/pwm_1khz.json", "--scenarios", str(tmp_path)]
    )
    assert res.exit_code == 2 and "not 'pwm_1khz'" in res.output


def test_batch_reports_llm_tokens_and_cost(pinmap, rig_profile, tmp_path) -> None:
    from grader.batch import format_table
    from grader.feedback import FEEDBACK_TOOL, LLMFeedback
    from grader.llm import FakeLLMClient, LLMConfig

    item = {
        "check_id": "pwm.frequency_hz",
        "explanation": "The prescaler halves the frequency.",
        "cited_value": 500,
        "code_location": None,
        "cause_found": True,
    }
    fake = FakeLLMClient([FakeLLMClient.tool_call(FEEDBACK_TOOL, {"items": [item]})])
    cfg = LLMConfig(model="test-model", price_input_per_mtok=2.0, price_output_per_mtok=10.0)
    rows, m = run_batch(
        load_plan(ROOT / "plans" / "pwm_1khz.json"),
        [ROOT / "scenarios/pwm/wrong_prescaler.yaml", ROOT / "scenarios/pwm/correct.yaml"],
        pinmap=pinmap,
        rig_profile=rig_profile,
        out_dir=tmp_path,
        feedback=LLMFeedback(fake, cfg),
        repo_root=ROOT,
        cost_usd=cfg.cost_usd,
    )
    # FakeLLMClient reports 100 input + 50 output tokens: 100*2/1e6 + 50*10/1e6 = $0.0007
    assert (m.llm_calls, m.input_tokens, m.output_tokens) == (1, 100, 50)
    assert m.cost_usd == pytest.approx(0.0007)
    with (tmp_path / "summary.csv").open(encoding="utf-8") as fh:
        table = {r["submission"]: r for r in csv.DictReader(fh)}
    called = table["pwm_wrong_prescaler"]
    assert (called["llm_input_tokens"], called["llm_output_tokens"]) == ("100", "50")
    assert called["llm_cost_usd"] == "0.000700"
    idle = table["pwm_correct"]  # nothing FAILed, so no call and blank LLM columns
    assert idle["llm_input_tokens"] == idle["llm_cost_usd"] == ""
    assert "LLM cost           : $0.0007 total" in format_table(rows, m)


def test_batch_without_feedback_has_blank_llm_columns(pinmap, rig_profile, tmp_path) -> None:
    _, m = run_batch(
        load_plan(ROOT / "plans" / "pwm_1khz.json"),
        [ROOT / "scenarios/pwm/wrong_prescaler.yaml"],
        pinmap=pinmap,
        rig_profile=rig_profile,
        out_dir=tmp_path,
    )
    assert m.llm_calls == 0 and m.cost_usd is None
    with (tmp_path / "summary.csv").open(encoding="utf-8") as fh:
        (r,) = list(csv.DictReader(fh))
    assert r["llm_input_tokens"] == r["llm_cost_usd"] == ""
