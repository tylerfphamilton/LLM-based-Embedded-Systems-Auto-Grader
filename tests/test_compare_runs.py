"""scripts/compare_runs.py: hardware batch vs code-only baseline from two summary.csv files."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("compare_runs", ROOT / "scripts/compare_runs.py")
assert _spec and _spec.loader
compare_runs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(compare_runs)

HW = """assignment,submission,ground_truth_faulty,fault,pass,fail,borderline,error,flagged,llm_input_tokens,llm_output_tokens,llm_latency_s,llm_cost_usd,elapsed_s
b,correct,false,,20,0,0,0,false,,,,,20.0
b,no_debounce,true,no_debounce,18,2,0,0,true,1000,500,3.0,0.010000,25.0
b,too_slow,true,too_slow,18,2,0,0,true,1000,500,3.0,0.010000,25.0
b,wrong_baud,true,wrong_baud,16,4,0,0,true,1000,500,3.0,0.010000,25.0
b,hw_only,true,x,0,1,0,0,true,,,,,1.0
"""  # noqa: E501

CODE = """submission,ground_truth_faulty,fault,pass,fail,unsure,flagged,error,llm_error,llm_input_tokens,llm_output_tokens,llm_latency_s,llm_cost_usd,elapsed_s
correct,false,,4,1,0,true,0,,2000,400,5.0,0.008000,5.0
no_debounce,true,no_debounce,5,0,1,false,0,,2000,400,5.0,0.008000,5.0
too_slow,true,too_slow,4,0,1,false,0,,2000,400,5.0,0.008000,5.0
wrong_baud,true,wrong_baud,4,1,0,true,0,,2000,400,5.0,0.008000,5.0
code_only,false,,5,0,0,false,0,,2000,400,5.0,0.008000,5.0
"""  # noqa: E501


def _runs(tmp_path: Path) -> tuple[Path, Path]:
    hw, code = tmp_path / "hw", tmp_path / "code"
    hw.mkdir(), code.mkdir()
    (hw / "summary.csv").write_text(HW, encoding="utf-8")
    (code / "summary.csv").write_text(CODE, encoding="utf-8")
    reqs = {"cost_usd": 0.02, "requirements": []}
    (code / "requirements.json").write_text(json.dumps(reqs), encoding="utf-8")
    return hw, code


def test_agreement_table_and_disagreements(tmp_path, capsys) -> None:
    hw, code = _runs(tmp_path)
    result = compare_runs.compare(compare_runs.read_summary(hw), compare_runs.read_summary(code))
    rows = {r["submission"]: r for r in result["table"]}
    assert rows["wrong_baud"] == {
        "submission": "wrong_baud", "truth": "wrong_baud", "hardware_flagged": True,
        "code_flagged": True, "code_unsure": 0, "agree": True,
    }  # fmt: skip
    assert rows["no_debounce"]["code_unsure"] == 1 and not rows["no_debounce"]["agree"]
    assert result["disagree"] == ["correct", "no_debounce", "too_slow"]
    assert (result["only_hw"], result["only_code"]) == (["hw_only"], ["code_only"])
    assert result["rates"]["hardware"] == (1.0, 0.0)
    assert result["rates"]["code"] == (1 / 3, 1.0)

    out_csv = tmp_path / "cmp.csv"
    assert compare_runs.main(["--hw", str(hw), "--code", str(code), "--csv", str(out_csv)]) == 0
    text = capsys.readouterr().out
    assert "hardware: detection 100.0%, false failures 0.0%" in text
    assert "code    : detection 33.3%, false failures 100.0%" in text
    assert "disagree: correct, no_debounce, too_slow" in text
    assert "only in the hardware run: hw_only" in text
    assert "cost hardware: $0.0060 per graded submission ($0.0300 total, 3 of 5 rows" in text
    assert "cost code    : $0.0120 per graded submission ($0.0600 total)" in text
    with out_csv.open(encoding="utf-8") as fh:
        saved = list(csv.DictReader(fh))
    assert saved[0] == {
        "submission": "correct", "truth": "correct", "hardware_flagged": "false",
        "code_flagged": "true", "code_unsure": "0", "agree": "false",
    }  # fmt: skip


def test_missing_summary_exits_2(tmp_path) -> None:
    assert compare_runs.main(["--hw", str(tmp_path), "--code", str(tmp_path)]) == 2
