from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from dbression import __version__
from dbression.parser import parse_suite, parse_test_file
from dbression.parser.markdown_writer import page_to_markdown
from dbression.parser.wiki import parse_wiki
from dbression.report import (
    ProgressObserver,
    make_progress,
    print_suite_result,
    render_run,
    write_json_report,
    write_junit_xml,
)
from dbression.runner import TagFilter, build_engine_for_suite, count_fixtures, run_suite

app = typer.Typer(
    name="dbression",
    help="Modern Python port of DBFit — regression tests for database schemas and business logic.",
    no_args_is_help=True,
    add_completion=False,
)

console = Console()


@app.callback()
def _main_callback() -> None:
    """Force multi-command mode so `dbression <subcommand>` works."""


@app.command()
def version() -> None:
    """Print the installed dbression version."""
    console.print(f"dbression {__version__}")


@app.command()
def run(
    path: Annotated[
        Path,
        typer.Argument(
            help="A suite directory (with _root.wiki) OR a single test file (.test.md / .wiki)"
        ),
    ],
    commit_mode: Annotated[
        str,
        typer.Option(
            "--commit-mode",
            help="'test' = rollback per test (default), 'page' = commit per page (DBFit-compatible)",
        ),
    ] = "test",
    verbose: Annotated[
        bool, typer.Option("-v", "--verbose", help="Print every fixture table, not just the page line")
    ] = False,
    details: Annotated[
        bool,
        typer.Option(
            "-d",
            "--details",
            help="Print each fixture's result (green/red) live as it runs, DBFit-web-UI style",
        ),
    ] = False,
    render: Annotated[
        bool,
        typer.Option(
            "-r",
            "--render",
            help="Render a single .test.md page in the terminal, cards lighting up green/red "
            "in place as fixtures run (DBFit-browser style). Single .test.md file only.",
        ),
    ] = False,
    progress: Annotated[
        bool | None,
        typer.Option(
            "--progress/--no-progress",
            help="Live spinner + x/y fixture counter (default: on when stdout is a terminal)",
        ),
    ] = None,
    tag: Annotated[
        list[str] | None,
        typer.Option(
            "--tag",
            help="Only run pages carrying this tag (front-matter `Suites:`); may be passed multiple times",
        ),
    ] = None,
    skip_tag: Annotated[
        list[str] | None,
        typer.Option("--skip-tag", help="Skip pages carrying this tag; may be passed multiple times"),
    ] = None,
    junit_xml: Annotated[
        Path | None,
        typer.Option("--junit-xml", help="Write a JUnit-XML report to this path (CI: Bitbucket/Jenkins)"),
    ] = None,
    json_report: Annotated[
        Path | None,
        typer.Option("--json", help="Write a JSON report to this path (LLM / tooling)"),
    ] = None,
) -> None:
    """Run a dbression test (single file) or suite (directory) with live progress."""
    if commit_mode not in ("test", "page"):
        console.print(
            f"[red]Invalid commit-mode: {commit_mode!r} (allowed: test, page)[/red]"
        )
        raise typer.Exit(2)

    tag_filter = TagFilter(only=tuple(tag or ()), skip=tuple(skip_tag or ()))

    if render and not (path.is_file() and path.name.endswith(".test.md")):
        console.print(
            "[red]--render works on a single .test.md file[/red] "
            "(it renders one page as a live document)."
        )
        raise typer.Exit(2)

    if path.is_dir():
        suite = parse_suite(path)
        kind = "Suite"
    elif path.is_file():
        try:
            suite = parse_test_file(path)
        except ValueError as e:
            console.print(f"[red]{e}[/red]")
            raise typer.Exit(2)
        kind = "Test"
    else:
        console.print(f"[red]Path does not exist:[/red] {path}")
        raise typer.Exit(2)

    engine = build_engine_for_suite(suite)
    console.print(
        f"dbression {__version__} — {kind}: [bold]{suite.name}[/bold] @ "
        f"{engine.url.render_as_string(hide_password=True)}\n"
    )

    # Progress is on by default at a TTY; --progress / --no-progress override.
    use_progress = console.is_terminal if progress is None else progress
    total = count_fixtures(suite, tag_filter)

    try:
        if render:
            # Live DBFit-style page render — the document IS the output.
            result = render_run(
                console,
                suite,
                engine,
                source=path.read_text(encoding="utf-8"),
                commit_mode=commit_mode,  # type: ignore[arg-type]
                tag_filter=tag_filter,
            )
        elif use_progress:
            with make_progress(console) as prog:
                task = prog.add_task("starting…", total=total or None)
                observer = ProgressObserver(console, prog, task, details=details)
                result = run_suite(
                    suite,
                    engine,
                    commit_mode=commit_mode,  # type: ignore[arg-type]
                    tag_filter=tag_filter,
                    observer=observer,
                )
        else:
            # No live bar (piped / CI). Still stream colored detail lines if asked.
            observer = ProgressObserver(console, details=details) if details else None
            result = run_suite(
                suite,
                engine,
                commit_mode=commit_mode,  # type: ignore[arg-type]
                tag_filter=tag_filter,
                observer=observer,
            )
    finally:
        engine.dispose()
    if not render:
        print_suite_result(result, console, verbose=verbose)

    if junit_xml is not None:
        write_junit_xml(result, junit_xml)
        console.print(f"[dim]JUnit-XML: {junit_xml}[/dim]")
    if json_report is not None:
        write_json_report(result, json_report)
        console.print(f"[dim]JSON report: {json_report}[/dim]")

    if result.error or result.failed_count > 0:
        raise typer.Exit(1)


@app.command()
def convert(
    path: Annotated[Path, typer.Argument(help="Path to a .wiki file OR a directory")],
    output: Annotated[
        Path | None,
        typer.Option(
            "-o",
            "--output",
            help="Destination path (file or directory); default: in-place next to the source",
        ),
    ] = None,
    force: Annotated[bool, typer.Option("-f", "--force", help="Overwrite existing .test.md")] = False,
) -> None:
    """Convert ``.wiki`` files (DBFit format) to ``.test.md`` (dbression's own format)."""
    if not path.exists():
        console.print(f"[red]Path does not exist:[/red] {path}")
        raise typer.Exit(2)

    wiki_files: list[Path] = []
    if path.is_file():
        if path.suffix != ".wiki":
            console.print(f"[red]Expected a .wiki file, got:[/red] {path}")
            raise typer.Exit(2)
        wiki_files.append(path)
    else:
        wiki_files = sorted(path.rglob("*.wiki"))
        if not wiki_files:
            console.print(f"[yellow]No .wiki files found under[/yellow] {path}")
            raise typer.Exit(0)

    written = 0
    skipped = 0
    for wf in wiki_files:
        target = _convert_target(wf, output, single_input=path.is_file())
        if target.exists() and not force:
            console.print(f"[yellow]⏭  exists, use --force to overwrite:[/yellow] {target}")
            skipped += 1
            continue
        page = parse_wiki(wf)
        md = page_to_markdown(page)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(md, encoding="utf-8")
        console.print(f"[green]✓[/green] {wf}  →  {target}")
        written += 1

    console.print(f"\n[bold]{written} file(s) written, {skipped} skipped[/bold]")


def _convert_target(wiki_file: Path, output: Path | None, single_input: bool) -> Path:
    """Compute the destination path for a converted .wiki file."""
    md_name = wiki_file.stem + ".test.md"
    if output is None:
        return wiki_file.parent / md_name
    if single_input:
        # output is either a file or a directory
        if output.suffix == ".md" or output.name.endswith(".test.md"):
            return output
        return output / md_name
    # Directory mode: output is the destination root, mirror the structure
    return output / md_name


def main() -> None:
    app()


if __name__ == "__main__":
    main()
