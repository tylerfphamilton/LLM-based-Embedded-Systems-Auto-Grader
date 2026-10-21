"""Command-line interface: ``grader export-schema | validate-plan | run | batch``."""

from __future__ import annotations

import contextlib
import sys
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from grader.batch import format_table, grade_scenario, run_batch
from grader.fake_rig import load_scenario
from grader.llm import (
    AnthropicClient,
    LLMError,
    load_llm_config,
    load_prompt,
    require_api_key,
)
from grader.pinmap import load_pinmap
from grader.plan import PlanError, export_schema, load_plan
from grader.planner import (
    PLAN_PROMPT,
    describe_request,
    first_request,
    generate_plan,
    load_meta,
    meta_path,
    write_outputs,
)
from grader.report import Report, write_reports
from grader.rig_profile import load_rig_profile
from grader.validate import validate_plan

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
) -> None:
    """Grade one submission and write report.json + report.md to OUT/<submission>/."""
    p = _load_plan_or_exit(plan, pinmap)
    pm, prof = load_pinmap(pinmap), load_rig_profile(profile)
    if rig is Rig.fake:
        if scenario is None:
            raise typer.BadParameter("--rig fake needs --scenario", param_hint="--scenario")
        try:
            report = grade_scenario(p, load_scenario(scenario), pinmap=pm, rig_profile=prof)
        except ValueError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(2) from None
    else:
        report = _run_serial(p, sketch, submission, port, board_port, pm, prof)
    directory = out / report.submission
    json_path, md_path = write_reports(report, directory)
    typer.echo(_summary_line(report))
    typer.echo(f"reports: {json_path}  {md_path}")


def _run_serial(plan, sketch, submission, port, board_port, pinmap, profile) -> Report:
    from grader.flasher import ArduinoCliFlasher, Submission
    from grader.runner import run as run_plan
    from grader.transport import SerialTransport, TransportError

    typer.secho(
        "WARNING: --rig serial is UNTESTED ON HARDWARE (SerialTransport + ArduinoCliFlasher). "
        "The firmware protocol is still a draft.",
        fg=typer.colors.YELLOW,
        err=True,
    )
    if sketch is None:
        raise typer.BadParameter("--rig serial needs --sketch", param_hint="--sketch")
    sub = Submission(submission or sketch.name, sketch)
    try:
        transport = SerialTransport(port)
    except (TransportError, ImportError) as exc:
        typer.echo(f"error: cannot open measuring board: {exc}", err=True)
        raise typer.Exit(2) from None
    with transport:
        return run_plan(
            plan, sub, ArduinoCliFlasher(port=board_port), transport, profile, pinmap=pinmap
        )


@app.command()
def batch(
    plan: Annotated[Path, typer.Option(help="Plan JSON file.")],
    scenarios: Annotated[Path, typer.Option(help="Directory of scenario YAML files.")],
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("out"),
    pinmap: PinmapOpt = DEFAULT_PINMAP,
    profile: ProfileOpt = DEFAULT_PROFILE,
) -> None:
    """Grade every scenario in a directory (fake rig) and print benchmark metrics."""
    p = _load_plan_or_exit(plan, pinmap)
    paths = sorted(scenarios.glob("*.yaml")) + sorted(scenarios.glob("*.yml"))
    if not paths:
        typer.echo(f"error: no scenario files in {scenarios}", err=True)
        raise typer.Exit(2)
    try:
        rows, metrics = run_batch(
            p,
            paths,
            pinmap=load_pinmap(pinmap),
            rig_profile=load_rig_profile(profile),
            out_dir=out,
        )
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from None
    typer.echo(f"Plan: {p.assignment}  ({len(rows)} scenarios)\n")
    typer.echo(format_table(rows, metrics))
    md = out / "<submission>" / "report.md"
    typer.echo(f"\nreports: {md}   summary: {out / 'summary.csv'}")


LLMConfigOpt = Annotated[Path, typer.Option("--llm-config", help="LLM settings YAML.")]
DEFAULT_LLM_CONFIG = Path("config/llm.yaml")


@app.command("make-plan")
def make_plan_cmd(
    handout: Annotated[Path, typer.Option(help="Assignment handout (Markdown or text).")],
    name: Annotated[str, typer.Option(help="Assignment name, e.g. pwm_1khz.")],
    pinmap: PinmapOpt = DEFAULT_PINMAP,
    llm_config: LLMConfigOpt = DEFAULT_LLM_CONFIG,
    out_dir: Annotated[Path, typer.Option(help="Plans directory.")] = Path("plans"),
    dry_run: Annotated[bool, typer.Option(help="Print the first request; no API call.")] = False,
    force: Annotated[bool, typer.Option(help="Overwrite an approved meta file.")] = False,
) -> None:
    """Draft a test plan from a handout with the LLM (writes plans/drafts/<name>.draft.json)."""
    cfg = load_llm_config(llm_config)
    req = first_request(
        name, handout.read_text(encoding="utf-8"), pinmap.read_text(encoding="utf-8"), cfg
    )
    if dry_run:
        typer.echo(describe_request(req, load_prompt(PLAN_PROMPT)[1]))
        return
    meta = load_meta(meta_path(out_dir / f"{name}.json"))
    if meta and meta.get("status") == "approved" and not force:
        typer.echo(
            f"error: {meta_path(out_dir / f'{name}.json')} is approved; "
            "use --force to replace it with a new draft",
            err=True,
        )
        raise typer.Exit(2)
    try:
        cfg.check()
        require_api_key()
        result = generate_plan(
            AnthropicClient.from_config(cfg), req, name=name, pinmap=load_pinmap(pinmap)
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
    typer.echo(f"draft: {paths['draft']}  ({result.attempts} attempt(s))")
    typer.echo(f"meta:  {paths['meta']}   log: {paths['log']}")
    typer.echo(
        f"Review the draft, copy it to {out_dir / (name + '.json')}, then run: "
        f"grader approve-plan {out_dir / (name + '.json')} --by <you>"
    )


if __name__ == "__main__":
    app()
