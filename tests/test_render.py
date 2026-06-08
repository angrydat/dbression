"""Tests for the live DBFit-style page renderer (report/render.py), against SQLite."""
from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from dbression.parser import parse_test_file
from dbression.report.render import (
    PageRenderer,
    _Fixture,
    _Prose,
    _strip_sql_preamble,
    parse_segments,
    render_run,
)
from dbression.runner import TagFilter, build_engine_for_suite


SAMPLE = """# Kunden

<!-- dbression:env=sqlite -->
Some prose here.

### Query

```sql
select 1 as n
```

| n |
|---|
| 1 |

### Execute Procedure foo

| a |
|---|
| 1 |
"""


def test_parse_segments_splits_prose_and_fixtures() -> None:
    segs = parse_segments(SAMPLE)
    fixtures = [s for s in segs if isinstance(s, _Fixture)]
    prose = [s for s in segs if isinstance(s, _Prose)]
    assert len(fixtures) == 2
    assert fixtures[0].title == "Query"
    assert fixtures[1].title == "Execute Procedure foo"
    # Directive comment is stripped from prose; the title heading is prose too.
    assert prose, "expected at least the preamble prose"
    assert "dbression:env" not in "\n".join(p.text_md for p in prose)


def test_strip_sql_preamble_removes_leading_sql_block() -> None:
    details = "SQL:\nselect 1\n\nExpected (n):\n  | 1 |"
    assert _strip_sql_preamble(details) == "Expected (n):\n  | 1 |"
    # No SQL preamble → unchanged.
    assert _strip_sql_preamble("Error: boom") == "Error: boom"


def test_page_renderer_state_transitions() -> None:
    segs = parse_segments(SAMPLE)
    r = PageRenderer(page_name="Kunden", segments=segs)
    assert len(r.fixtures) == 2
    assert all(f.state == "pending" for f in r.fixtures)

    r.mark_running(0)
    assert r.fixtures[0].state == "running"

    from dbression.fixtures.base import FixtureResult

    r.mark_result(0, FixtureResult(passed=True, message="ok"), 0.01)
    assert r.fixtures[0].state == "pass"

    # Second fixture never ran → finalize marks it skipped.
    r.finalize(passed=1, failed=0)
    assert r.fixtures[1].state == "skip"
    assert r.finished is True

    # Renders without raising (force terminal so Rich actually paints).
    console = Console(force_terminal=True, width=80)
    with console.capture() as cap:
        console.print(r)
    out = cap.get()
    assert "Kunden" in out


@pytest.fixture
def render_suite(tmp_path: Path) -> Path:
    (tmp_path / "connection.properties").write_text("service=:memory:\n")
    (tmp_path / "_root.wiki").write_text(
        "!|DatabaseEnvironment|sqlite|\n|ConnectUsingFile|connection.properties|\n"
    )
    (tmp_path / "SuiteSetUp.test.md").write_text(
        "# Setup\n\n### Execute\n```sql\ncreate table t (n int)\n```\n\n"
        "### Execute\n```sql\ninsert into t values (1)\n```\n"
    )
    f = tmp_path / "OneTest.test.md"
    f.write_text(
        "# One\n\n### Query\n```sql\nselect n from t\n```\n\n| n |\n|---|\n| 1 |\n\n"
        "### Query\n```sql\nselect n from t\n```\n\n| n |\n|---|\n| 99 |\n"
    )
    return f


def test_render_run_end_to_end(render_suite: Path) -> None:
    console = Console(force_terminal=True, width=80)
    suite = parse_test_file(render_suite)
    engine = build_engine_for_suite(suite)
    try:
        result = render_run(
            console, suite, engine, source=render_suite.read_text(), tag_filter=TagFilter()
        )
    finally:
        engine.dispose()
    # One page, first Query passes, second fails (expects 99) → page fails overall.
    page = result.pages[0]
    assert [t.result.passed for t in page.tables] == [True, False]
