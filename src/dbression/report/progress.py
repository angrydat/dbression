"""Live progress + optional per-fixture detail output for ``dbression run``.

Two things this module provides:

* :func:`make_progress` — a Rich ``Progress`` with a spinner, an ``x/y`` fixture counter,
  the elapsed time, and a status line showing which fixture/query is currently running.
* :class:`ProgressObserver` — a :class:`~dbression.runner.RunObserver` that drives the
  progress bar and, in ``--details`` mode, prints a colored pass/fail line per fixture
  (DBFit-web-UI style) above the live bar.

The observer is deliberately defensive about Rich markup: fixture names and SQL contain
``[…]`` (MSSQL identifiers, array literals) which Rich would otherwise interpret as style
tags. All dynamic text is rendered through ``rich.text.Text`` (no markup parsing).
"""
from __future__ import annotations

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.text import Text

from dbression.fixtures.base import FixtureResult
from dbression.parser.ast import Table
from dbression.runner import RunObserver


def make_progress(console: Console) -> Progress:
    """Build the live progress display (spinner + status + x/y counter + elapsed)."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=None),
        MofNCompleteColumn(),
        TextColumn("fixtures"),
        TimeElapsedColumn(),
        console=console,
        transient=True,  # clear the bar when done so the summary stands alone
    )


def _fixture_preview(table: Table, maxlen: int = 72) -> str:
    """A one-line, whitespace-collapsed preview of what this fixture runs."""
    text = " ".join(str(a) for a in table.header_args)
    text = " ".join(text.split())
    if len(text) > maxlen:
        text = text[: maxlen - 1] + "…"
    return text


class ProgressObserver(RunObserver):
    """Drive a Rich ``Progress`` task and optionally print per-fixture detail lines.

    Works in two modes:

    * with a ``progress``/``task_id`` (TTY): updates the live bar and, if ``details``,
      prints detail lines above it via the progress console.
    * without a progress bar (non-TTY but ``details`` requested): prints detail lines
      straight to ``console``.
    """

    def __init__(
        self,
        console: Console,
        progress: Progress | None = None,
        task_id: int | None = None,
        *,
        details: bool = False,
    ) -> None:
        self.console = console
        self.progress = progress
        self.task_id = task_id
        self.details = details

    def _out(self) -> Console:
        return self.progress.console if self.progress is not None else self.console

    def on_fixture_start(self, page_name: str, table: Table) -> None:
        if self.progress is None or self.task_id is None:
            return
        preview = _fixture_preview(table)
        label = f"{page_name} › {table.name}"
        if preview:
            label += f": {preview}"
        # Description is rendered with markup; Text() keeps brackets literal.
        self.progress.update(self.task_id, description=Text(label, style="cyan"))

    def on_fixture_end(
        self, page_name: str, table: Table, result: FixtureResult, duration: float
    ) -> None:
        if self.progress is not None and self.task_id is not None:
            self.progress.advance(self.task_id)
        if not self.details:
            return
        line = Text()
        if result.passed:
            line.append("✓ ", style="bold green")
        else:
            line.append("✗ ", style="bold red")
        line.append(page_name, style="bold")
        line.append(" › ")
        line.append(table.name, style="" if result.passed else "red")
        line.append(f"  {duration * 1000:.0f}ms", style="dim")
        self._out().print(line)
        if result.message:
            self._out().print(
                Text("    " + result.message, style="dim" if result.passed else "red")
            )
