"""pytest-inspired console reporter using rich."""
from __future__ import annotations

from rich.console import Console

from dbression.runner import PageResult, SuiteResult


_PASS = "[green]✓[/green]"
_FAIL = "[red]✗[/red]"
_SKIP = "[yellow]⊝[/yellow]"


def print_suite_result(suite_result: SuiteResult, console: Console, verbose: bool = False) -> None:
    """Print a pytest-style summary of the suite results (recursively)."""
    _print_suite_body(suite_result, console, verbose, indent=0)

    # Collect failures flat
    failures = list(_collect_failures(suite_result))
    if failures:
        console.rule("[bold red]FAILURES[/bold red]")
        for kind, page in failures:
            console.print(f"\n[bold]{page.path}[/bold] :: [red]{page.name}[/red] ({kind})")
            _print_page_details(page, console)

    # Summary
    total = suite_result.total_count
    passed = suite_result.passed_count
    failed = suite_result.failed_count
    summary_color = "green" if failed == 0 and not failures else "red"
    console.rule(
        f"[bold {summary_color}]{passed} passed, {failed} failed "
        f"(of {total} pages)[/bold {summary_color}]"
    )


def _print_suite_body(
    sr: SuiteResult, console: Console, verbose: bool, indent: int
) -> None:
    pad = "  " * indent
    if sr.error:
        console.print(f"{pad}[red]Suite aborted[/red] {sr.name}: {sr.error}")

    if sr.setup_result and not sr.setup_result.passed:
        console.print(f"{pad}[red]SuiteSetUp FAILED[/red] — {sr.name}")

    if sr.pages or sr.setup_result or sr.teardown_result:
        if indent > 0:
            console.print(f"{pad}[bold]{sr.name}/[/bold]")

    for page in sr.pages:
        _print_page_line(page, console, verbose, indent=indent + (1 if indent > 0 else 0))

    for sub in sr.subsuites:
        _print_suite_body(sub, console, verbose, indent=indent + 1)

    if sr.teardown_result and not sr.teardown_result.passed:
        console.print(f"{pad}[red]SuiteTearDown FAILED[/red] — {sr.name}")


def _collect_failures(sr: SuiteResult):
    if sr.setup_result and not sr.setup_result.passed:
        yield ("SuiteSetUp", sr.setup_result)
    for p in sr.pages:
        if not p.passed:
            yield ("Test", p)
    if sr.teardown_result and not sr.teardown_result.passed:
        yield ("SuiteTearDown", sr.teardown_result)
    for sub in sr.subsuites:
        yield from _collect_failures(sub)


def _print_page_line(page: PageResult, console: Console, verbose: bool, indent: int = 1) -> None:
    pad = "  " * indent
    total = sum(t.duration for t in page.tables)
    if page.error:
        marker = _FAIL
        suffix = f"[red] error: {page.error}[/red]"
    elif page.passed:
        marker = _PASS
        suffix = ""
    else:
        marker = _FAIL
        suffix = ""
    console.print(f"{pad}{marker} {page.name:<40} {total:6.3f}s{suffix}")
    if verbose:
        for t in page.tables:
            sub_marker = _PASS if t.result.passed else _FAIL
            console.print(f"{pad}    {sub_marker} {t.name} — {t.result.message}")


def _print_page_details(page: PageResult, console: Console) -> None:
    if page.error:
        console.print(f"  [red]{page.error}[/red]")
        return
    for t in page.tables:
        if t.result.passed:
            continue
        console.print(f"  [red]{t.name}[/red]: {t.result.message}")
        if t.result.details:
            console.print()
            for line in t.result.details.splitlines():
                console.print(f"    {line}")
