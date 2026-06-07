"""Tests for the run observer, fixture counting, single-file runs, and the progress
observer — all against in-memory SQLite (no server needed)."""
from __future__ import annotations

from pathlib import Path

import pytest
from rich.console import Console

from dbression.fixtures.base import FixtureResult
from dbression.parser import parse_suite, parse_test_file
from dbression.parser.ast import Table
from dbression.report.progress import ProgressObserver, _fixture_preview, make_progress
from dbression.runner import (
    RunObserver,
    TagFilter,
    build_engine_for_suite,
    count_fixtures,
    run_suite,
)


@pytest.fixture
def demo_suite(tmp_path: Path) -> Path:
    (tmp_path / "connection.properties").write_text("service=:memory:\n")
    (tmp_path / "_root.wiki").write_text(
        "!|DatabaseEnvironment|sqlite|\n|ConnectUsingFile|connection.properties|\n"
    )
    (tmp_path / "SuiteSetUp.test.md").write_text(
        "# Setup\n\n### Execute\n```sql\ncreate table t (n int)\n```\n\n"
        "### Execute\n```sql\ninsert into t values (1),(2),(3)\n```\n"
    )
    (tmp_path / "CountTest.test.md").write_text(
        "# Count\n\n### Query\n```sql\nselect count(*) as c from t\n```\n\n| c |\n|---|\n| 3 |\n"
    )
    return tmp_path


def test_count_fixtures_matches_observed(demo_suite: Path) -> None:
    suite = parse_suite(demo_suite)
    total = count_fixtures(suite, TagFilter())
    # 2 setup Execute + 1 page Query = 3 (DatabaseEnvironment/ConnectUsingFile excluded)
    assert total == 3

    class Recorder(RunObserver):
        def __init__(self) -> None:
            self.started: list[str] = []
            self.ended: list[bool] = []

        def on_fixture_start(self, page_name: str, table: Table) -> None:
            self.started.append(f"{page_name}:{table.name}")

        def on_fixture_end(self, page_name, table, result, duration) -> None:
            self.ended.append(result.passed)

    rec = Recorder()
    engine = build_engine_for_suite(suite)
    try:
        result = run_suite(suite, engine, observer=rec)
    finally:
        engine.dispose()

    assert result.passed_count == 1
    assert len(rec.started) == total
    assert len(rec.ended) == total
    assert all(rec.ended)


def test_single_file_run_pulls_in_setup(demo_suite: Path) -> None:
    """Running just the test file must still run SuiteSetUp + use _root connection."""
    suite = parse_test_file(demo_suite / "CountTest.test.md")
    assert suite.name == "CountTest"
    assert suite.setup is not None  # SuiteSetUp pulled in
    assert len(suite.pages) == 1  # exactly one test, no siblings

    engine = build_engine_for_suite(suite)
    try:
        result = run_suite(suite, engine)
    finally:
        engine.dispose()
    assert result.passed_count == 1, result.error


def test_self_contained_markdown_file(tmp_path: Path) -> None:
    (tmp_path / "connection.properties").write_text("service=:memory:\n")
    f = tmp_path / "Solo.test.md"
    f.write_text(
        "# Solo\n\n<!-- dbression:env=sqlite -->\n"
        "<!-- dbression:connection=connection.properties -->\n\n"
        "### Query\n```sql\nselect 1 as n\n```\n\n| n |\n|---|\n| 1 |\n"
    )
    suite = parse_test_file(f)
    assert suite.setup is None  # no SuiteSetUp in dir
    engine = build_engine_for_suite(suite)  # config comes from the file's own directives
    try:
        result = run_suite(suite, engine)
    finally:
        engine.dispose()
    assert result.passed_count == 1, result.error


def test_parse_test_file_rejects_unknown_extension(tmp_path: Path) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text("hello")
    with pytest.raises(ValueError):
        parse_test_file(bad)


def test_fixture_preview_collapses_and_truncates() -> None:
    t = Table(name="Query", header_args=["select   *\n  from   foo"])
    assert _fixture_preview(t) == "select * from foo"
    long = Table(name="Query", header_args=["x" * 200])
    assert len(_fixture_preview(long)) <= 72


def test_progress_observer_handles_bracket_identifiers(demo_suite: Path) -> None:
    """A fixture name/SQL with [brackets] must not break Rich markup parsing."""
    console = Console(force_terminal=True, width=100)
    with make_progress(console) as prog:
        task = prog.add_task("…", total=2)
        obs = ProgressObserver(console, prog, task, details=True)
        tbl = Table(name="Query", header_args=["select * from [dbo].[ORDER]"])
        obs.on_fixture_start("PageA", tbl)
        obs.on_fixture_end("PageA", tbl, FixtureResult(passed=True, message="OK [x]"), 0.01)
        obs.on_fixture_end(
            "PageA", tbl, FixtureResult(passed=False, message="boom [y]"), 0.02
        )
    # No exception == markup-safe.
