"""Command-line interface: ``grader export-schema | validate-plan | run | batch |
make-plan | wiring | code-grade``."""

from __future__ import annotations

import contextlib
import re
import sys
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from grader.batch import format_table, grade_scenario, require_params, run_batch
from grader.fake_rig import load_scenario
from grader.feedback import FeedbackGenerator, LLMFeedback
from grader.llm import (
    MODEL_PLACEHOLDER,
    AnthropicClient,
    LLMError,
    load_llm_config,
    load_prompt,
    require_api_key,
)
from grader.pinmap import load_pinmap
from grader.plan import PARAM_PATTERN, PlanError, export_schema, load_plan
from grader.planner import (
    PLAN_PROMPT,
    describe_request,
    first_request,
    generate_plan,
    write_outputs,
)
from grader.report import Report, write_reports
from grader.rig_profile import load_rig_profile
from grader.validate import validate_plan
from grader.wiring import WiringError, guide_text, write_wiring

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Host-side autograder for Arduino embedded-systems assignments.",
)

PinmapOpt = Annotated[Path, typer.Option("--pinmap", help="Pin map YAML.")]
ProfileOpt = Annotated[Path, typer.Option("--profile", help="Rig profile YAML.")]
DEFAULT_PINMAP = Path("config/pinmap.yaml")
DEFAULT_PROFILE = Path("config/rig_profile.yaml")


class Rig(StrEnum):
    fake = "fake"
    serial = "serial"


class FeedbackKind(StrEnum):
    none = "none"
    llm = "llm"


FeedbackOpt = Annotated[
    FeedbackKind, typer.Option("--feedback", help="none, or llm (one API call per FAIL report).")
]
LLMConfigOpt = Annotated[Path, typer.Option("--llm-config", help="LLM settings YAML.")]
DEFAULT_LLM_CONFIG = Path("config/llm.yaml")


def _feedback_or_exit(kind: FeedbackKind, llm_config: Path) -> FeedbackGenerator | None:
    """Build the feedback hook. With llm, a missing key or model stops before any grading."""
    if kind is FeedbackKind.none:
        return None
    cfg = load_llm_config(llm_config)
    try:
        cfg.check()
        require_api_key()
    except LLMError as exc:
        typer.echo(f"error: --feedback llm: {exc}", err=True)
        raise typer.Exit(2) from None
    return LLMFeedback(AnthropicClient.from_config(cfg), cfg)


def _utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]


def _load_plan_or_exit(path: Path, pinmap_path: Path):
    try:
        plan = load_plan(path)
    except PlanError as exc:
        _print_errors(path, exc.errors)
        raise typer.Exit(1) from None
    errors = validate_plan(plan, load_pinmap(pinmap_path))
    if errors:
        _print_errors(path, errors)
        raise typer.Exit(1)
    return plan


def _pairs_or_exit(items: list[str] | None, option: str) -> dict[str, str]:
    """``NAME=VALUE`` options as a dict; a malformed one exits 2."""
    out = {}
    for item in items or []:
        name, sep, value = item.partition("=")
        if not sep or not re.fullmatch(PARAM_PATTERN, name):
            typer.echo(
                f"error: {option} {item!r}: expected NAME=VALUE with a lower-case name, "
                "e.g. student_id=000412387",
                err=True,
            )
            raise typer.Exit(2)
        out[name] = value
    return out


def _print_errors(path: Path, errors: list[str]) -> None:
    typer.echo(f"{path}: {len(errors)} error(s)", err=True)
    for e in errors:
        typer.echo(f"  - {e}", err=True)


def _summary_line(report: Report) -> str:
    s = report.summary
    return (
        f"{report.submission}: {s.PASS}/{s.graded} PASS, {s.FAIL} FAIL, "
        f"{s.BORDERLINE} BORDERLINE, {s.ERROR} ERROR, {s.NOT_GRADED} NOT_GRADED"
    )


@app.callback()
def _main() -> None:
    _utf8_console()


@app.command("export-schema")
def export_schema_cmd(
    out: Annotated[Path, typer.Option(help="Where to write the schema.")] = Path(
        "schemas/plan.schema.json"
    ),
    check: Annotated[bool, typer.Option(help="Only check that OUT is up to date.")] = False,
) -> None:
    """Write the plan JSON Schema (generated from the pydantic models)."""
    text = export_schema()
    if check:
        current = out.read_text(encoding="utf-8") if out.exists() else ""
        if current != text:
            typer.echo(f"{out} is stale; run: grader export-schema", err=True)
            raise typer.Exit(1)
        typer.echo(f"{out} is up to date")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    typer.echo(f"wrote {out}")


@app.command("validate-plan")
def validate_plan_cmd(
    plan: Annotated[Path, typer.Argument(help="Plan JSON file.")],
    pinmap: PinmapOpt = DEFAULT_PINMAP,
) -> None:
    """Check a plan against the schema and the pin map; print every error."""
    p = _load_plan_or_exit(plan, pinmap)
    n = sum(1 for s in p.steps if s.op == "measure")
    typer.echo(f"{plan}: OK ({len(p.steps)} steps, {n} measurements)")


@app.command()
def run(
    plan: Annotated[Path, typer.Option(help="Plan JSON file.")],
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("out"),
    rig: Annotated[Rig, typer.Option(help="fake (scenario) or serial (hardware).")] = Rig.fake,
    scenario: Annotated[Path | None, typer.Option(help="Scenario YAML (fake rig).")] = None,
    sketch: Annotated[Path | None, typer.Option(help="Sketch directory (serial rig).")] = None,
    submission: Annotated[str | None, typer.Option(help="Submission id (serial rig).")] = None,
    port: Annotated[str | None, typer.Option(help="Measuring-board port (serial).")] = None,
    board_port: Annotated[str | None, typer.Option(help="Student-board port (serial).")] = None,
    pinmap: PinmapOpt = DEFAULT_PINMAP,
    profile: ProfileOpt = DEFAULT_PROFILE,
    feedback: FeedbackOpt = FeedbackKind.none,
    llm_config: LLMConfigOpt = DEFAULT_LLM_CONFIG,
    param: Annotated[
        list[str] | None,
        typer.Option("--param", help="Per-student value NAME=VALUE (repeatable)."),
    ] = None,
) -> None:
    """Grade one submission and write report.json + report.md to OUT/<submission>/."""
    values = _pairs_or_exit(param, "--param")
    p = _load_plan_or_exit(plan, pinmap)
    fb = _feedback_or_exit(feedback, llm_config)
    warnings: list[str] = []  # plan warnings in the report (none since D68)
    pm, prof = load_pinmap(pinmap), load_rig_profile(profile)
    if rig is Rig.fake:
        if scenario is None:
            raise typer.BadParameter("--rig fake needs --scenario", param_hint="--scenario")
        try:
            sc = load_scenario(scenario)
            require_params(p, {sc.submission: {**sc.params, **values}})
            report = grade_scenario(
                p, sc, pinmap=pm, rig_profile=prof, feedback=fb, plan_warnings=warnings,
                params=values,
            )  # fmt: skip
        except ValueError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(2) from None
    else:
        sub_id = submission or (sketch.name if sketch else "")
        try:
            require_params(p, {sub_id: values})
        except ValueError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(2) from None
        report = _run_serial(
            p, sketch, submission, port, board_port, pm, prof, warnings, fb, values
        )
    directory = out / report.submission
    json_path, md_path = write_reports(report, directory)
    typer.echo(_summary_line(report))
    typer.echo(f"reports: {json_path}  {md_path}")


def _run_serial(
    plan, sketch, submission, port, board_port, pinmap, profile, warnings, feedback, values
) -> Report:
    from grader.flasher import ArduinoCliFlasher, Submission
    from grader.runner import run as run_plan
    from grader.transport import SerialTransport, TransportError

    if sketch is None:
        raise typer.BadParameter("--rig serial needs --sketch", param_hint="--sketch")
    sub = Submission(submission or sketch.name, sketch, params=values)
    try:
        transport = SerialTransport(port)
    except (TransportError, ImportError) as exc:
        typer.echo(f"error: cannot open measuring board: {exc}", err=True)
        raise typer.Exit(2) from None
    with transport:
        return run_plan(
            plan,
            sub,
            ArduinoCliFlasher(port=board_port),
            transport,
            profile,
            feedback,
            pinmap=pinmap,
            plan_warnings=warnings,
        )


@app.command()
def batch(
    plan: Annotated[Path, typer.Option(help="Plan JSON file.")],
    scenarios: Annotated[
        Path | None, typer.Option(help="Directory of scenario YAML files (fake rig).")
    ] = None,
    submissions: Annotated[
        Path | None,
        typer.Option(help="Directory of sketch folders X/X.ino, plus labels.yaml (serial rig)."),
    ] = None,
    rig: Annotated[Rig, typer.Option(help="fake (scenarios) or serial (hardware).")] = Rig.fake,
    port: Annotated[str | None, typer.Option(help="Measuring-board port (serial).")] = None,
    board_port: Annotated[str | None, typer.Option(help="Student-board port (serial).")] = None,
    flash_only: Annotated[
        bool, typer.Option(help="Serial only: compile and upload each sketch, no measuring.")
    ] = False,
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("out"),
    pinmap: PinmapOpt = DEFAULT_PINMAP,
    profile: ProfileOpt = DEFAULT_PROFILE,
    feedback: FeedbackOpt = FeedbackKind.none,
    llm_config: LLMConfigOpt = DEFAULT_LLM_CONFIG,
) -> None:
    """Grade every scenario (fake rig) or sketch folder (serial rig); print benchmark metrics."""
    folder = _batch_folder_or_exit(rig, scenarios, submissions, flash_only, feedback)
    p = _load_plan_or_exit(plan, pinmap)
    if rig is Rig.serial:
        _serial_batch(
            p,
            plan,
            folder,
            port,
            board_port,
            flash_only,
            out,
            pinmap,
            profile,
            feedback,
            llm_config,
        )
        return
    fb = _feedback_or_exit(feedback, llm_config)
    cost = load_llm_config(llm_config).cost_usd if fb is not None else None
    warnings: list[str] = []  # plan warnings in the report (none since D68)
    paths = sorted(folder.glob("*.yaml")) + sorted(folder.glob("*.yml"))
    if not paths:
        typer.echo(f"error: no scenario files in {folder}", err=True)
        raise typer.Exit(2)
    try:
        rows, metrics = run_batch(
            p,
            paths,
            pinmap=load_pinmap(pinmap),
            rig_profile=load_rig_profile(profile),
            out_dir=out,
            feedback=fb,
            plan_warnings=warnings,
            cost_usd=cost,
        )
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from None
    typer.echo(f"Plan: {p.assignment}  ({len(rows)} scenarios)\n")
    typer.echo(format_table(rows, metrics))
    md = out / "<submission>" / "report.md"
    typer.echo(f"\nreports: {md}   summary: {out / 'summary.csv'}")


def _batch_folder_or_exit(rig, scenarios, submissions, flash_only, feedback) -> Path:
    """Check the option combination for ``batch``; return the folder to read."""

    def bad(problem: str):
        typer.echo(f"error: {problem}", err=True)
        raise typer.Exit(2)

    if rig is Rig.fake:
        if flash_only:
            bad("--flash-only needs --rig serial")
        if submissions is not None:
            bad("--submissions needs --rig serial (the fake rig reads --scenarios)")
        if scenarios is None:
            bad("--rig fake needs --scenarios")
        folder = scenarios
    else:
        if scenarios is not None:
            bad("--rig serial reads --submissions, not --scenarios")
        if submissions is None:
            bad("--rig serial needs --submissions")
        if flash_only and feedback is FeedbackKind.llm:
            bad("--flash-only does not grade, so it cannot use --feedback llm")
        folder = submissions
    if not folder.is_dir():
        bad(f"{folder} is not a directory")
    return folder


def _serial_batch(
    p, plan_path, folder, port, board_port, flash_only, out, pinmap, profile, feedback, llm_config
) -> None:
    from grader.batch import (
        discover_submissions,
        flash_only_batch,
        format_flash_table,
        load_labels,
        load_params,
        run_serial_batch,
    )
    from grader.flasher import ArduinoCliFlasher
    from grader.transport import SerialTransport, TransportError

    subs = discover_submissions(folder)
    if not subs:
        typer.echo(f"error: no sketch folders (X/X.ino) in {folder}", err=True)
        raise typer.Exit(2)
    labels = load_labels(folder)
    flasher = ArduinoCliFlasher(port=board_port)
    if flash_only:
        rows = flash_only_batch(subs, labels, flasher=flasher, out_dir=out)
        typer.echo("\n" + format_flash_table(rows))
        logs = out / "<submission>" / "flash.log"
        typer.echo(f"\nlogs: {logs}   summary: {out / 'flash_summary.csv'}")
        return
    try:  # before the port is opened: a missing value is the instructor's to fix
        params = load_params(folder)
        require_params(p, {s.id: params.get(s.id, {}) for s in subs})
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from None
    fb = _feedback_or_exit(feedback, llm_config)
    cost = load_llm_config(llm_config).cost_usd if fb is not None else None
    warnings: list[str] = []  # plan warnings in the report (none since D68)
    try:
        transport = SerialTransport(port)
    except (TransportError, ImportError) as exc:
        typer.echo(f"error: cannot open measuring board: {exc}", err=True)
        raise typer.Exit(2) from None
    try:
        with transport:
            rows, metrics, stopped = run_serial_batch(
                p,
                subs,
                labels,
                transport=transport,
                flasher=flasher,
                pinmap=load_pinmap(pinmap),
                rig_profile=load_rig_profile(profile),
                out_dir=out,
                feedback=fb,
                plan_warnings=warnings,
                cost_usd=cost,
                params=params,
            )
    except KeyboardInterrupt:
        typer.echo(f"\ninterrupted; partial summary: {out / 'summary.csv'}", err=True)
        raise typer.Exit(130) from None
    typer.echo(f"Plan: {p.assignment}  ({len(rows)} of {len(subs)} submissions)\n")
    typer.echo(format_table(rows, metrics))
    md = out / "<submission>" / "report.md"
    typer.echo(f"\nreports: {md}   summary: {out / 'summary.csv'}")
    if stopped:
        typer.echo(f"error: {stopped}", err=True)
        raise typer.Exit(1)


@app.command("make-plan")
def make_plan_cmd(
    handout: Annotated[Path, typer.Option(help="Assignment handout (Markdown or text).")],
    name: Annotated[str, typer.Option(help="Assignment name, e.g. pwm_1khz.")],
    pinmap: PinmapOpt = DEFAULT_PINMAP,
    llm_config: LLMConfigOpt = DEFAULT_LLM_CONFIG,
    out_dir: Annotated[Path, typer.Option(help="Plans directory.")] = Path("plans"),
    dry_run: Annotated[bool, typer.Option(help="Print the first request; no API call.")] = False,
    force: Annotated[bool, typer.Option(help="Replace an existing plans/<name>.json.")] = False,
    param_doc: Annotated[
        list[str] | None,
        typer.Option(
            "--param-doc", help='Per-student value NAME="description" for the plan (repeatable).'
        ),
    ] = None,
) -> None:
    """Generate a test plan from a handout with the LLM (writes plans/<name>.json)."""
    docs = _pairs_or_exit(param_doc, "--param-doc")
    cfg = load_llm_config(llm_config)
    req = first_request(
        name, handout.read_text(encoding="utf-8"), pinmap.read_text(encoding="utf-8"), cfg, docs
    )
    if dry_run:
        typer.echo(describe_request(req, load_prompt(PLAN_PROMPT)[1]))
        return
    target = out_dir / f"{name}.json"
    if target.exists() and not force:  # checked before any API call
        typer.echo(f"error: {target} already exists; use --force to replace it", err=True)
        raise typer.Exit(2)
    try:
        cfg.check()
        require_api_key()
        result = generate_plan(
            AnthropicClient.from_config(cfg),
            req,
            name=name,
            pinmap=load_pinmap(pinmap),
            params=list(docs),
        )
    except LLMError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from None
    paths = write_outputs(
        result, name=name, handout_path=handout, out_dir=out_dir, now=datetime.now(UTC)
    )
    if not result.ok:
        _print_errors(Path(f"{name} (after {result.attempts} attempts)"), result.errors)
        typer.echo(f"log: {paths['log']}", err=True)
        raise typer.Exit(1)
    typer.echo(f"plan: {paths['plan']}  ({result.attempts} attempt(s))")
    typer.echo(f"meta: {paths['meta']}   log: {paths['log']}")
    try:
        guide = write_wiring(load_plan(paths["plan"]), load_pinmap(pinmap), paths["plan"], pinmap)
    except WiringError as exc:
        typer.echo(f"error: no wiring guide, the plan can't be wired yet: {exc}", err=True)
        typer.echo(f"The plan was kept: {paths['plan']}", err=True)
        raise typer.Exit(2) from None
    typer.echo(f"wiring: {guide}")
    typer.echo("Read the plan's assumptions before grading with it.")


@app.command()
def wiring(
    plan: Annotated[Path, typer.Option(help="Plan JSON file.")],
    pinmap: PinmapOpt = DEFAULT_PINMAP,
    out: Annotated[
        Path | None,
        typer.Option(help="Where to write (default: plans/wiring_guides/<name>.wiring.md)."),
    ] = None,
    print_: Annotated[bool, typer.Option("--print", help="Write to stdout instead.")] = False,
) -> None:
    """Write the plan's wiring guide (which wires, which resistors) from the pin map."""
    p = _load_plan_or_exit(plan, pinmap)
    pm = load_pinmap(pinmap)
    try:
        if print_:
            typer.echo(guide_text(p, pm, plan, pinmap), nl=False)
            return
        target = write_wiring(p, pm, plan, pinmap, out)
    except WiringError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from None
    typer.echo(f"wrote {target}")


@app.command("code-grade")
def code_grade_cmd(
    handout: Annotated[Path, typer.Option(help="Assignment handout (Markdown or text).")],
    submissions: Annotated[
        Path, typer.Option(help="Directory of sketch folders X/X.ino (+ labels.yaml, params.yaml).")
    ],
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("out/code"),
    requirements: Annotated[
        Path | None, typer.Option(help="Reuse a saved requirements.json (no requirements call).")
    ] = None,
    model: Annotated[str | None, typer.Option(help="Model ID (default: model.code_grade).")] = None,
    llm_config: LLMConfigOpt = DEFAULT_LLM_CONFIG,
) -> None:
    """Baseline: an LLM grades each sketch by reading the code (no rig, no plan; D66)."""
    from grader import code_grade as cg
    from grader.batch import discover_submissions, load_labels, load_params

    def stop(problem: str, code: int = 2):
        typer.echo(f"error: {problem}", err=True)
        raise typer.Exit(code)

    cfg = load_llm_config(llm_config)
    model_id = model or cfg.code_grade_model
    if not model_id or model_id == MODEL_PLACEHOLDER:
        stop(f"{llm_config}: 'model' is still the placeholder; set a current Claude model ID.")
    try:
        require_api_key()
    except LLMError as exc:
        stop(str(exc))
    if not submissions.is_dir():
        stop(f"{submissions} is not a directory")
    subs = discover_submissions(submissions)
    if not subs:
        stop(f"no sketch folders (X/X.ino) in {submissions}")
    try:
        params = load_params(submissions)
        reused = cg.load_requirements(requirements) if requirements else None
    except (ValueError, OSError) as exc:
        stop(str(exc))
    client = AnthropicClient.from_config(cfg)
    if reused is not None:
        doc = reused
        cg.write_requirements(doc, None, out)
    else:
        try:
            doc, result = cg.make_requirements(client, handout, cfg, model_id)
        except LLMError as exc:
            stop(str(exc))
        path = cg.write_requirements(doc, result, out)
        if not result.ok:
            _print_errors(Path(f"requirements (after {result.attempts} attempts)"), result.errors)
            stop(f"no valid requirement list; see {path.with_name('requirements.log.json')}", 1)
        typer.echo(
            f"requirements: {path} ({len(doc['requirements'])}, {result.attempts} attempt(s))"
        )
    rows, metrics = cg.run_code_grade(
        client, cfg, model_id, handout.read_text(encoding="utf-8"), doc["requirements"], subs,
        load_labels(submissions), params, out,
    )  # fmt: skip
    typer.echo(f"\nCode-only baseline: {model_id}  ({len(rows)} submissions)\n")
    typer.echo(cg.format_table(rows, metrics, doc))
    typer.echo(
        f"\nreports: {out / '<submission>' / 'code_grade.md'}   summary: {out / 'summary.csv'}"
    )


if __name__ == "__main__":
    app()
