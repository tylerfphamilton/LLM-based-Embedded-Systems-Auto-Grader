"""Per-student values (plan params, D63): loading, validation, instantiation, batches, CLI,
make-plan and redaction of LLM requests. No hardware, no network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import grader.flasher
import grader.transport
from grader import cli
from grader.batch import (
    MissingParamsError,
    grade_scenario,
    load_labels,
    load_params,
    run_batch,
    run_serial_batch,
)
from grader.compare import Verdict
from grader.fake_rig import load_scenario
from grader.feedback import FEEDBACK_TOOL, LLMFeedback
from grader.flasher import Flasher, FlashResult, Submission
from grader.llm import FakeLLMClient, LLMConfig, load_llm_config
from grader.plan import PlanError, instantiate, load_plan, parse_plan
from grader.planner import PLAN_TOOL, check_draft, first_request, generate_plan
from grader.report import write_reports
from grader.transport import FakeTransport
from grader.validate import validate_plan

ROOT = Path(__file__).resolve().parent.parent
UART_PLAN = ROOT / "plans" / "uart_id.json"
UART_SCENARIOS = sorted((ROOT / "scenarios" / "uart_id").glob("*.yaml"))
runner = CliRunner()


def _raw() -> dict:
    return json.loads(UART_PLAN.read_text(encoding="utf-8"))


def _errors(raw: dict, pinmap) -> list[str]:
    try:
        return validate_plan(parse_plan(raw), pinmap)
    except PlanError as exc:
        return exc.errors


# ------------------------------------------------------------------------ loading


def test_params_yaml_loads_with_integers_as_strings(tmp_path, capsys) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "a.ino").write_text("", encoding="utf-8")
    (tmp_path / "params.yaml").write_text(
        'a: { student_id: "000412387", digit_sum: 25 }\nghost: { student_id: "000000001" }\n',
        encoding="utf-8",
    )
    params = load_params(tmp_path)
    assert params["a"] == {"student_id": "000412387", "digit_sum": "25"}
    assert "'ghost' has no matching submission folder" in capsys.readouterr().err


def test_missing_params_file_means_no_params(tmp_path) -> None:
    assert load_params(tmp_path) == {}


def test_benchmark_params_are_consistent() -> None:
    folder = ROOT / "benchmark" / "uart_id"
    params = load_params(folder)  # warns while the sketches don't exist yet
    assert params.keys() == load_labels(folder).keys()
    for v in params.values():
        sid = v["student_id"]
        assert len(sid) == 9 and sid.startswith("000")
        assert v["digit_sum"] == str(sum(map(int, sid)))
        assert v["id_hex"] == format(int(sid), "X")


# --------------------------------------------------------------------- validation


def test_uart_plan_template_is_valid(pinmap) -> None:
    assert validate_plan(load_plan(UART_PLAN), pinmap) == []


def test_undeclared_placeholder_is_an_error(pinmap) -> None:
    raw = _raw()
    raw["steps"][2]["expect"][0]["value"] = "^{{student_nr}}$"
    errors = _errors(raw, pinmap)
    assert "step 'id_lf': placeholder {{student_nr}} in 'expect[0].value' is not declared" in (
        " ".join(errors)
    )


def test_declared_but_unused_param_is_an_error(pinmap) -> None:
    raw = _raw()
    raw["params"].append("email")
    assert "params: 'email' is declared but never used as {{email}}." in _errors(raw, pinmap)


@pytest.mark.parametrize(
    ("index", "key", "value"),
    [
        (0, "field", "{{student_id}}"),  # a field name, not a text value
        (1, "value", "{{digit_sum}}"),  # a value on the numeric field framing_errors
    ],
)
def test_placeholder_outside_a_text_field_is_an_error(pinmap, index, key, value) -> None:
    raw = _raw()
    raw["steps"][2]["expect"][index][key] = value
    field = f"expect[{index}].{key}"
    errors = " ".join(_errors(raw, pinmap))
    assert f"field '{field}' contains {value}, but placeholders are only allowed" in errors


def test_placeholder_in_a_number_is_a_schema_error() -> None:
    raw = _raw()
    raw["steps"][2]["window_ms"] = "{{digit_sum}}"
    with pytest.raises(PlanError):
        parse_plan(raw)


def test_plan_without_params_is_unchanged(pinmap) -> None:
    plan = load_plan(ROOT / "plans" / "pwm_1khz.json")
    assert plan.params == [] and instantiate(plan, {}) is plan
    assert validate_plan(plan, pinmap) == []


# -------------------------------------------------------------------- instantiate

VALUES = {"student_id": "000412387", "digit_sum": "25", "id_hex": "64AE3"}


def test_instantiate_fills_text_values_and_uart_data(pinmap) -> None:
    raw = _raw()
    raw["steps"][3]["data"] = "ID {{student_id}}\n"  # send_id_lf
    raw["steps"][2]["expect"].append({"field": "text", "op": "contains", "value": "{{id_hex}}"})
    plan = instantiate(parse_plan(raw), VALUES)
    assert plan.params == [] and validate_plan(plan, pinmap) == []
    assert plan.steps[2].expect[0].value == "^000412387\\r?\\n$"
    assert plan.steps[2].expect[2].value == "64AE3"
    assert plan.steps[3].data == "ID 000412387\n"


def test_instantiate_escapes_regex_only_in_matches() -> None:
    raw = _raw()
    raw["steps"][3]["data"] = "{{id_hex}}"
    plan = instantiate(parse_plan(raw), {**VALUES, "id_hex": "1.5+x"})
    assert plan.steps[6].expect[0].value == "^1\\.5\\+x\\r?\\n$"  # hex: matches
    assert plan.steps[3].data == "1.5+x"  # raw value outside matches


def test_instantiate_missing_value_names_the_param() -> None:
    with pytest.raises(PlanError, match="no value for param 'id_hex'"):
        instantiate(load_plan(UART_PLAN), {"student_id": "1", "digit_sum": "1"})


# -------------------------------------------------------------------------- batch


def test_fake_uart_batch_gives_expected_verdicts(pinmap, rig_profile, tmp_path) -> None:
    _, m = run_batch(
        load_plan(UART_PLAN), UART_SCENARIOS, pinmap=pinmap, rig_profile=rig_profile,
        out_dir=tmp_path,
    )  # fmt: skip
    assert (m.faulty, m.correct, m.detection_rate, m.false_failure_rate) == (3, 1, 1.0, 0.0)
    assert m.error_checks == 0
    report = json.loads((tmp_path / "uart_id_correct" / "report.json").read_text("utf-8"))
    assert report["params"] == VALUES


def test_scenario_missing_a_param_stops_the_batch(pinmap, rig_profile, tmp_path) -> None:
    text = (ROOT / "scenarios/uart_id/correct.yaml").read_text(encoding="utf-8")
    bad = tmp_path / "scen"
    bad.mkdir()
    (bad / "x.yaml").write_text(text.replace(', id_hex: "64AE3"', ""), encoding="utf-8")
    with pytest.raises(MissingParamsError, match="uart_id_correct: id_hex"):
        run_batch(load_plan(UART_PLAN), [bad / "x.yaml"], pinmap=pinmap, rig_profile=rig_profile)
    res = runner.invoke(
        cli.app,
        ["batch", "--plan", str(UART_PLAN), "--scenarios", str(bad), "--out", str(tmp_path / "o")],
    )
    assert res.exit_code == 2 and "uart_id_correct: id_hex" in res.output
    assert not (tmp_path / "o").exists()


class NeverFlasher(Flasher):
    kind = "test"

    def flash(self, submission: Submission) -> FlashResult:
        raise AssertionError("graded although a param was missing")


def test_serial_batch_missing_param_stops_before_grading(pinmap, rig_profile, tmp_path) -> None:
    subs = [Submission("a", tmp_path), Submission("b", tmp_path)]
    params = {"a": VALUES, "b": {"student_id": "000000001"}}
    with pytest.raises(MissingParamsError) as exc:
        run_serial_batch(
            load_plan(UART_PLAN), subs, {}, transport=FakeTransport(None), flasher=NeverFlasher(),
            pinmap=pinmap, rig_profile=rig_profile, out_dir=tmp_path / "o", params=params,
        )  # fmt: skip
    assert "b: digit_sum, id_hex" in str(exc.value) and "a:" not in str(exc.value)


def test_cli_serial_batch_missing_param_exits_2_before_opening_port(tmp_path, monkeypatch) -> None:
    for n in ("a", "b"):
        (tmp_path / n).mkdir()
        (tmp_path / n / f"{n}.ino").write_text("", encoding="utf-8")
    (tmp_path / "params.yaml").write_text(
        'a: { student_id: "000412387", digit_sum: 25, id_hex: "64AE3" }\n', encoding="utf-8"
    )
    monkeypatch.setattr(grader.transport, "SerialTransport", lambda *a: pytest.fail("opened"))
    monkeypatch.setattr(grader.flasher, "ArduinoCliFlasher", lambda **kw: NeverFlasher())
    res = runner.invoke(
        cli.app,
        ["batch", "--plan", str(UART_PLAN), "--submissions", str(tmp_path), "--rig", "serial",
         "--out", str(tmp_path / "o")],
    )  # fmt: skip
    assert res.exit_code == 2, res.output
    assert "b: student_id, digit_sum, id_hex" in res.output


# --------------------------------------------------------------------- grader run


def test_cli_run_param_overrides_scenario(tmp_path) -> None:
    scen = str(ROOT / "scenarios/uart_id/correct.yaml")
    res = runner.invoke(
        cli.app,
        ["run", "--plan", str(UART_PLAN), "--scenario", scen, "--out", str(tmp_path),
         "--param", "digit_sum=26"],
    )  # fmt: skip
    assert res.exit_code == 0, res.output
    report = json.loads((tmp_path / "uart_id_correct" / "report.json").read_text("utf-8"))
    assert report["params"]["digit_sum"] == "26"
    assert {c["id"]: c["verdict"] for c in report["checks"]}["sum.text"] == "FAIL"


@pytest.mark.parametrize("bad", ["student_id", "Student=1", "=1"])
def test_cli_run_malformed_param_exits_2(bad) -> None:
    res = runner.invoke(
        cli.app,
        ["run", "--plan", str(UART_PLAN), "--scenario", str(UART_SCENARIOS[0]), "--param", bad],
    )
    assert res.exit_code == 2 and "expected NAME=VALUE" in res.output


# ---------------------------------------------------------------------- make-plan

DOCS = {"student_id": "the student's 9-digit ID", "digit_sum": "sum of the ID's digits",
        "id_hex": "the ID as upper-case hex"}  # fmt: skip


def _handout_request(docs):
    handout = (ROOT / "handouts" / "uart_id.md").read_text(encoding="utf-8")
    pm = (ROOT / "config" / "pinmap.yaml").read_text(encoding="utf-8")
    return first_request("uart_id", handout, pm, LLMConfig(model="test-model"), docs)


def test_param_docs_in_user_message_and_expected_params(pinmap) -> None:
    user = _handout_request(DOCS).messages[0]["content"]
    assert "- {{student_id}}: the student's 9-digit ID" in user
    assert "<params>\nnone\n</params>" in _handout_request({}).messages[0]["content"]
    assert check_draft(_raw(), "uart_id", pinmap, list(DOCS)) == []
    assert "params: must be exactly" in " ".join(check_draft(_raw(), "uart_id", pinmap, []))
    fake = FakeLLMClient([FakeLLMClient.tool_call(PLAN_TOOL, _raw())])
    result = generate_plan(
        fake, _handout_request(DOCS), name="uart_id", pinmap=pinmap, params=list(DOCS)
    )
    assert result.ok and result.raw_plan["params"] == list(DOCS)


def test_make_plan_dry_run_lists_param_docs() -> None:
    res = runner.invoke(
        cli.app,
        ["make-plan", "--handout", str(ROOT / "handouts/uart_id.md"), "--name", "uart_id_llm",
         "--llm-config", str(ROOT / "config/llm.yaml"), "--dry-run",
         "--param-doc", "student_id=the student's 9-digit ID"],
    )  # fmt: skip
    assert res.exit_code == 0, res.output
    assert "- {{student_id}}: the student's 9-digit ID" in res.output
    assert "Per-student values" in res.output  # the system prompt section
    bad = runner.invoke(
        cli.app,
        ["make-plan", "--handout", str(ROOT / "handouts/uart_id.md"), "--name", "x",
         "--dry-run", "--param-doc", "no_equals_sign"],
    )  # fmt: skip
    assert bad.exit_code == 2


# ---------------------------------------------------------------------- redaction

SID = "000638205"  # copied_id's own ID; its sketch prints 000412387


def _item(cid, cited, text, loc=None):
    return {"check_id": cid, "explanation": text, "cited_value": cited, "code_location": loc,
            "cause_found": True, "same_cause_as": None}  # fmt: skip


def _copied_id_with_feedback(pinmap, rig_profile, tmp_path, items):
    sketch = tmp_path / "copied_id"
    sketch.mkdir()
    (sketch / "copied_id.ino").write_text(
        f'// my id is {SID}\nconst char *ID = "000412387";\n', encoding="utf-8"
    )
    scenario = load_scenario(ROOT / "scenarios/uart_id/copied_id.yaml")
    scenario = scenario.model_copy(update={"sketch": sketch})
    fake = FakeLLMClient([FakeLLMClient.tool_call(FEEDBACK_TOOL, {"items": items})])
    cfg = LLMConfig(model="test-model")
    report = grade_scenario(
        load_plan(UART_PLAN), scenario, pinmap=pinmap, rig_profile=rig_profile,
        feedback=LLMFeedback(fake, cfg), repo_root=tmp_path,
    )  # fmt: skip
    return report, fake


def test_feedback_request_contains_no_student_id(pinmap, rig_profile, tmp_path) -> None:
    items = [
        _item("id_lf.text", "^<student_id>\\r?\\n$", "Print <student_id>, not 000412387.",
              "copied_id.ino:2 (<student_id>)"),
    ]  # fmt: skip
    report, fake = _copied_id_with_feedback(pinmap, rig_profile, tmp_path, items)
    (req,) = fake.requests
    sent = json.dumps({"system": req.system, "messages": req.messages})
    assert SID not in sent and "<student_id>" in sent
    assert "000412387" in sent  # the measured (copied) ID is not this student's: kept
    checks = {c.id: c for c in report.checks}
    # Cited value was checked against the redacted expected value, and accepted.
    assert checks["id_lf.text"].feedback == f"Print {SID}, not 000412387."
    assert checks["id_lf.text"].code_location == f"copied_id.ino:2 ({SID})"
    assert checks["id_lf.text"].verdict == Verdict.FAIL and report.params["student_id"] == SID
    write_reports(report, tmp_path / "out")
    saved = (tmp_path / "out" / "llm_feedback.json").read_text(encoding="utf-8")
    assert SID not in saved


def test_cited_real_value_is_rejected_after_redaction(pinmap, rig_profile, tmp_path) -> None:
    # The model never saw the real ID, so citing it means the citation is not from the data.
    items = [_item("id_lf.text", f"^{SID}\\r?\\n$", "x")]
    report, _ = _copied_id_with_feedback(pinmap, rig_profile, tmp_path, items)
    assert {c.id: c for c in report.checks}["id_lf.text"].feedback is None


def test_redact_params_config(tmp_path) -> None:
    assert load_llm_config(ROOT / "config/llm.yaml").redact_params == ("student_id",)
    (tmp_path / "a.yaml").write_text("model: m\nredact_params: []\n", encoding="utf-8")
    assert load_llm_config(tmp_path / "a.yaml").redact_params == ()
    (tmp_path / "b.yaml").write_text("model: m\n", encoding="utf-8")
    assert load_llm_config(tmp_path / "b.yaml").redact_params == ("student_id",)
