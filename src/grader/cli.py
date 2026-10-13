"""Command-line interface: ``grader export-schema | validate-plan | run | batch``."""

from __future__ import annotations

import contextlib
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from grader.batch import format_table, grade_scenario, run_batch
from grader.fake_rig import load_scenario
from grader.pinmap import load_pinmap
from grader.plan import PlanError, export_schema, load_plan
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


if __name__ == "__main__":
    app()
