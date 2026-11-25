"""Code-only baseline (D66) with FakeLLMClient: requirements, grading, metrics, values,
config and the CLI. No hardware, no network."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from grader import cli
from grader import code_grade as cg
from grader.batch import compute_metrics
from grader.fake_rig import GroundTruth
from grader.flasher import Submission
from grader.llm import FakeLLMClient, LLMConfig, LLMError, load_llm_config

ROOT = Path(__file__).resolve().parent.parent
CFG = LLMConfig(model="test-model")
runner = CliRunner()

REQS = [
    {"id": "led_on", "requirement": "The LED turns on when pressed."},
    {"id": "prints_id", "requirement": "ID? replies with the ID."},
    {"id": "uses_serial1", "requirement": "Replies on Serial1 at 9600 baud."},
]


def _req_call(reqs=REQS, n=1):
    return FakeLLMClient.tool_call(cg.REQ_TOOL, {"requirements": reqs}, n=n)


def _item(rid, verdict="PASS", reason="Looks right.", loc=None):
    return {"id": rid, "verdict": verdict, "reason": reason, "code_location": loc}


def _grade_call(*items):
    return FakeLLMClient.tool_call(cg.GRADE_TOOL, {"items": list(items)})


ALL_PASS = (_item("led_on"), _item("prints_id"), _item("uses_serial1"))


def _sketches(folder: Path, *names: str, code: str = "void setup() {}\nvoid loop() {}\n"):
    for n in names:
        (folder / n).mkdir(parents=True)
        (folder / n / f"{n}.ino").write_text(code, encoding="utf-8")
    (folder / "labels.yaml").write_text(
        "\n".join(f"{n}: {{ faulty: {str(n != 'good').lower()} }}" for n in names) + "\n",
        encoding="utf-8",
    )
    return folder


def _cli(monkeypatch, tmp_path, fake, *extra, config="model: test-model\n"):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(cli.AnthropicClient, "from_config", classmethod(lambda cls, cfg: fake))
    cfg = tmp_path / "llm.yaml"
    cfg.write_text(config, encoding="utf-8")
    return runner.invoke(
        cli.app,
        ["code-grade", "--handout", str(ROOT / "handouts/button_toggle.md"),
         "--submissions", str(tmp_path / "subs"), "--out", str(tmp_path / "out"),
         "--llm-config", str(cfg), *extra],
    )  # fmt: skip


# ----------------------------------------------------------------------- requirements


def test_valid_requirements_are_saved_and_graded(monkeypatch, tmp_path) -> None:
    _sketches(tmp_path / "subs", "bad", "good")
    fake = FakeLLMClient([_req_call(), _grade_call(*ALL_PASS), _grade_call(*ALL_PASS)])
    res = _cli(monkeypatch, tmp_path, fake)
    assert res.exit_code == 0, res.output
    doc = json.loads((tmp_path / "out/requirements.json").read_text(encoding="utf-8"))
    assert doc["requirements"] == REQS and doc["model"] == "test-model"
    assert doc["tokens"] == {"input": 100, "output": 50} and len(doc["prompt_version"]) == 8
    assert [r.tool["name"] for r in fake.requests] == [cg.REQ_TOOL] + [cg.GRADE_TOOL] * 2
    for n in ("bad", "good"):
        assert (tmp_path / "out" / n / "code_grade.json").exists()
        md = (tmp_path / "out" / n / "code_grade.md").read_text(encoding="utf-8")
        assert "Replies on Serial1 at 9600 baud." in md and "Kind" not in md
    assert "[1/2] bad: reading the code..." in res.output
    assert "LLM calls          : 3 (2 grading + 1 requirements)" in res.output


def test_invalid_requirements_are_repaired(tmp_path) -> None:
    bad = [
        {"id": "a", "requirement": "x"},
        {"id": "a", "requirement": "y"},
        {"id": "b", "requirement": "  "},
    ]
    fake = FakeLLMClient([_req_call(bad, 1), _req_call(REQS, 2)])
    handout = tmp_path / "h.md"
    handout.write_text("Blink.", encoding="utf-8")
    doc, result = cg.make_requirements(fake, handout, CFG, "test-model")
    assert result.ok and result.attempts == 2 and doc["requirements"] == REQS
    sent = fake.requests[1].messages[-1]["content"][0]
    assert sent["type"] == "tool_result" and sent["is_error"] is True
    assert "requirement #2 ('a'): id 'a' is already used" in sent["content"]
    assert "requirement #3 ('b'): the requirement sentence is empty." in sent["content"]


def test_three_invalid_requirement_lists_exit_nonzero(monkeypatch, tmp_path) -> None:
    _sketches(tmp_path / "subs", "good")
    bad = [{"id": "Bad Id", "requirement": "x"}]
    fake = FakeLLMClient([_req_call(bad, n) for n in (1, 2, 3)])
    res = _cli(monkeypatch, tmp_path, fake)
    assert res.exit_code == 1 and "id must be snake_case" in res.output
    assert len(fake.requests) == 3  # no grading call
    assert (tmp_path / "out/requirements.log.json").exists()


def test_requirements_file_makes_no_requirements_call(monkeypatch, tmp_path) -> None:
    _sketches(tmp_path / "subs", "good")
    saved = tmp_path / "reqs.json"
    saved.write_text(json.dumps({"model": "m", "requirements": REQS}), encoding="utf-8")
    fake = FakeLLMClient([_grade_call(*ALL_PASS)])
    res = _cli(monkeypatch, tmp_path, fake, "--requirements", str(saved))
    assert res.exit_code == 0, res.output
    assert [r.tool["name"] for r in fake.requests] == [cg.GRADE_TOOL]
    assert "0 requirements, list reused" in res.output
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    assert _cli(monkeypatch, tmp_path, FakeLLMClient([]), "--requirements", str(bad)).exit_code == 2


# ---------------------------------------------------------------------------- grading


def test_unknown_duplicate_and_invalid_items_are_dropped(tmp_path) -> None:
    fake = FakeLLMClient(
        [_grade_call(_item("led_on", "FAIL"), _item("led_on"), _item("nope"),
                     _item("prints_id", "MAYBE"), {"verdict": "PASS"})]
    )  # fmt: skip
    result = cg.grade_submission(fake, CFG, "test-model", "h", REQS, Submission("s", tmp_path))
    got = {q["id"]: q["verdict"] for q in result["requirements"]}
    assert got == {"led_on": "FAIL", "prints_id": "UNSURE", "uses_serial1": "UNSURE"}
    w = " | ".join(result["warnings"])
    assert "second item for 'led_on'" in w and "'nope' is not a requirement id" in w
    assert "invalid verdict 'MAYBE'" in w and "malformed" in w
    assert "no verdict for: prints_id, uses_serial1" in w
    unsure = next(q for q in result["requirements"] if q["id"] == "prints_id")
    assert unsure["reason"] == cg.NO_VERDICT


def test_llm_error_is_error_and_the_next_submission_is_graded(tmp_path, capsys) -> None:
    subs = [Submission("a", tmp_path), Submission("b", tmp_path)]
    fake = FakeLLMClient([LLMError("boom"), _grade_call(*ALL_PASS)])
    rows, m = cg.run_code_grade(fake, CFG, "test-model", "h", REQS, subs, {}, {}, tmp_path)
    assert len(fake.requests) == 2  # one call per submission
    assert (rows[0].errors, rows[0].llm_error, rows[1].passed) == (3, "boom", 3)
    saved = json.loads((tmp_path / "a" / "code_grade.json").read_text(encoding="utf-8"))
    assert {q["verdict"] for q in saved["requirements"]} == {"ERROR"}
    assert m.error_checks == 3 and "a: LLM error: boom" in capsys.readouterr().out


def test_cut_off_answer_is_error_not_unsure(tmp_path) -> None:
    cut = _grade_call(_item("led_on"))  # the tool call stopped part-way through
    cut.raw["stop_reason"] = "max_tokens"
    no_items = FakeLLMClient.tool_call(cg.GRADE_TOOL, {})
    for resp, why in ((cut, "cut off at max_tokens"), (no_items, "has no 'items' list")):
        sub = Submission("s", tmp_path)
        result = cg.grade_submission(FakeLLMClient([resp]), CFG, "test-model", "h", REQS, sub)
        assert {q["verdict"] for q in result["requirements"]} == {"ERROR"}
        assert why in result["llm"]["error"]
        assert result["llm"]["output_tokens"] == 50  # the spent tokens are still counted
        assert "response" in result["raw"]


# ---------------------------------------------------------------------------- metrics


def _row(name, faulty, verdicts):
    reqs = [{"id": f"r{i}", "requirement": "x", "verdict": v, "reason": ""}
            for i, v in enumerate(verdicts)]  # fmt: skip
    llm = {"input_tokens": 0, "output_tokens": 0, "latency_s": 0.0, "cost_usd": None,
           "error": None}  # fmt: skip
    result = {"submission": name, "requirements": reqs, "llm": llm}
    return cg.code_row(result, GroundTruth(faulty=faulty), Path("."), 0.0)


def test_unsure_does_not_flag_and_rates_are_right(tmp_path) -> None:
    rows = [
        _row("bug_found", True, ["FAIL", "PASS"]),
        _row("bug_unsure", True, ["UNSURE", "PASS"]),
        _row("bug_missed", True, ["PASS"]),
        _row("ok", False, ["PASS", "PASS"]),
        _row("ok_false_fail", False, ["FAIL"]),
    ]
    assert not rows[1].flagged and rows[1].borderline == 1  # UNSURE alone
    m = compute_metrics(rows)
    assert m.detection_rate == pytest.approx(1 / 3) and m.false_failure_rate == 0.5
    assert (m.borderline_checks, m.submissions_with_borderline) == (1, 1)
    cg.write_summary_csv(rows, tmp_path / "summary.csv")
    with (tmp_path / "summary.csv").open(encoding="utf-8") as fh:
        table = {r["submission"]: r for r in csv.DictReader(fh)}
    assert table["bug_unsure"]["flagged"] == "false" and table["bug_unsure"]["unsure"] == "1"
    assert "code_only_fail" not in table["ok"] and table["ok_false_fail"]["fail"] == "1"
    text = cg.format_table(rows, m, {"requirements": REQS, "attempts": 1})
    assert "Bug detection rate : 33.3%" in text and "UNSURE checks      : 1" in text
    assert "code_only" not in text and "NOTE" not in text


def test_old_saved_list_with_kind_still_loads(tmp_path) -> None:
    old = tmp_path / "old.json"
    old.write_text(json.dumps({"requirements": [{**REQS[0], "kind": "behaviour"}]}), "utf-8")
    assert cg.load_requirements(old)["requirements"] == [REQS[0]]


# ----------------------------------------------------------------------------- values

SID = "000412387"


def test_student_values_are_redacted_and_restored(tmp_path) -> None:
    sketch = tmp_path / "s"
    sketch.mkdir()
    (sketch / "s.ino").write_text(f'const char *ID = "{SID}";\n', encoding="utf-8")
    sub = Submission("s", sketch, params={"student_id": SID, "digit_sum": "25"})
    reason = "Prints <student_id> as required (line 1)."
    fake = FakeLLMClient([_grade_call(_item("prints_id", reason=reason, loc="s.ino:1"))])
    result = cg.grade_submission(fake, CFG, "test-model", "h", REQS, sub)
    user = fake.requests[0].messages[0]["content"]
    assert SID not in user
    values = user.split("<student_values>\n")[1].split("\n</student_values>")[0]
    assert values == "- student_id: <student_id>\n- digit_sum: 25"
    assert 'const char *ID = "<student_id>";' in user.split("<student_code")[1]
    item = next(q for q in result["requirements"] if q["id"] == "prints_id")
    assert item["reason"] == f"Prints {SID} as required (line 1)."
    assert SID not in json.dumps(result["raw"])  # the saved request and response


# ----------------------------------------------------------------------------- config


def test_code_grade_model_defaults_and_overrides(monkeypatch, tmp_path) -> None:
    assert load_llm_config(ROOT / "config/llm.yaml").code_grade_model == "claude-sonnet-5"
    split = "model: {feedback: fb-model, code_grade: cg-model}\n"
    (tmp_path / "a.yaml").write_text(split, encoding="utf-8")
    cfg = load_llm_config(tmp_path / "a.yaml")
    assert (cfg.code_grade_model, cfg.model, cfg.code_grade_max_tokens) == (
        "cg-model", "fb-model", 16000
    )  # fmt: skip
    _sketches(tmp_path / "subs", "good")
    fake = FakeLLMClient([_req_call(), _grade_call(*ALL_PASS)])
    assert _cli(monkeypatch, tmp_path, fake, config=split).exit_code == 0
    assert {r.model for r in fake.requests} == {"cg-model"}
    fake = FakeLLMClient([_req_call(), _grade_call(*ALL_PASS)])
    res = _cli(monkeypatch, tmp_path, fake, "--model", "cli-model", "--out", str(tmp_path / "o2"))
    assert res.exit_code == 0 and {r.model for r in fake.requests} == {"cli-model"}


def test_placeholder_model_or_missing_key_stops_before_any_call(monkeypatch, tmp_path) -> None:
    _sketches(tmp_path / "subs", "good")
    fake = FakeLLMClient([])
    res = _cli(monkeypatch, tmp_path, fake, config="max_retries: 1\n")
    assert res.exit_code == 2 and "placeholder" in res.output and not fake.requests
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    res = runner.invoke(
        cli.app,
        ["code-grade", "--handout", str(ROOT / "handouts/button_toggle.md"),
         "--submissions", str(tmp_path / "subs"), "--llm-config", str(ROOT / "config/llm.yaml")],
    )  # fmt: skip
    assert res.exit_code == 2 and "ANTHROPIC_API_KEY is not set" in res.output


def test_per_model_and_flat_prices(tmp_path) -> None:
    (tmp_path / "p.yaml").write_text(
        "model: {feedback: fb, code_grade: cg}\nprice_per_mtok:\n  input: 2.0\n  output: 10.0\n"
        "  cg: { input: 1.0, output: 5.0 }\n",
        encoding="utf-8",
    )
    cfg = load_llm_config(tmp_path / "p.yaml")
    assert cfg.cost_for("cg", 1_000_000, 1_000_000) == pytest.approx(6.0)
    assert cfg.cost_usd(1_000_000, 1_000_000) == pytest.approx(12.0)  # flat = feedback model
    assert cfg.cost_for("fb", 1_000_000, 0) == pytest.approx(2.0)
    assert cfg.cost_for("unknown", 10, 10) is None
    flat = load_llm_config(ROOT / "config/llm.yaml")
    assert flat.cost_usd(100, 50) == pytest.approx(0.0007) and flat.prices == {}
