from __future__ import annotations

from pathlib import Path

import pytest

from dbression.parser import parse_suite, parse_wiki

KBG_SUITE = Path.home() / "devel" / "ma31-ora" / "test" / "KBGSuite"


def test_parse_root_wiki(tmp_path: Path) -> None:
    src = tmp_path / "_root.wiki"
    src.write_text(
        "!path lib/*.jar\n"
        "\n"
        "!|import fixture|\n"
        "|dbfit.fixture|\n"
        "\n"
        "!|DatabaseEnvironment|oracle|\n"
        "|ConnectUsingFile|/path/to/file.properties|\n"
        "\n"
        "!1 Some Heading\n"
        "!contents -R2\n",
        encoding="utf-8",
    )
    page = parse_wiki(src)
    assert page.name == "_root"

    dir_names = [d.name for d in page.directives]
    assert "path" in dir_names

    fixture_names = [t.name for t in page.tables]
    assert fixture_names == ["import fixture", "DatabaseEnvironment", "ConnectUsingFile"]

    db_env = page.tables[1]
    assert db_env.header_args == ["oracle"]
    cu = page.tables[2]
    assert cu.name == "ConnectUsingFile"
    assert cu.header_args == ["/path/to/file.properties"]


def test_parse_query_with_multiline_escape(tmp_path: Path) -> None:
    src = tmp_path / "T.wiki"
    src.write_text(
        "!|Query|!-\n"
        "  select a, b\n"
        "  from t\n"
        "  where x is not null\n"
        "-!|\n"
        "|A|B|\n"
        "|1|hello|\n"
        "|2|world|\n",
        encoding="utf-8",
    )
    page = parse_wiki(src)
    assert len(page.tables) == 1
    tbl = page.tables[0]
    assert tbl.name == "Query"
    assert "select a, b" in tbl.header_args[0]
    assert tbl.headers == ["A", "B"]
    assert tbl.rows == [["1", "hello"], ["2", "world"]]


def test_front_matter_tags(tmp_path: Path) -> None:
    src = tmp_path / "T.wiki"
    src.write_text(
        "---\n"
        "Suites: critical NotOnCI\n"
        "Other: ignored\n"
        "---\n"
        "!|Query|select 1|\n"
        "|n|\n"
        "|1|\n",
        encoding="utf-8",
    )
    page = parse_wiki(src)
    assert page.tags == ["critical", "NotOnCI"]
    assert len(page.tables) == 1
    assert page.tables[0].name == "Query"


def test_no_front_matter(tmp_path: Path) -> None:
    src = tmp_path / "T.wiki"
    src.write_text("!|Query|select 1|\n|n|\n|1|\n", encoding="utf-8")
    page = parse_wiki(src)
    assert page.tags == []
    assert len(page.tables) == 1


def test_capture_symbol_header(tmp_path: Path) -> None:
    src = tmp_path / "T.wiki"
    src.write_text(
        "!|Query|select 42 as id from dual|\n"
        "|>>my_id|\n"
        "|42|\n",
        encoding="utf-8",
    )
    page = parse_wiki(src)
    tbl = page.tables[0]
    assert tbl.headers == [">>my_id"]
    assert tbl.rows == [["42"]]


@pytest.mark.skipif(not KBG_SUITE.is_dir(), reason="KBGSuite corpus not available")
def test_parse_kbg_suite_no_exceptions() -> None:
    """Smoke test: KBGSuite must parse end-to-end without raising."""
    suite = parse_suite(KBG_SUITE)
    assert suite.root_page is not None, "_root.wiki missing from parse result"
    assert suite.setup is not None, "SuiteSetUp.wiki missing"
    assert suite.teardown is not None, "SuiteTearDown.wiki missing"
    assert len(suite.pages) >= 6, f"Expected at least 6 test pages, found: {len(suite.pages)}"

    # Expected fixture names must appear somewhere in the suite
    all_fixtures = {
        t.name
        for p in [suite.root_page, suite.setup, suite.teardown, *suite.pages]
        if p is not None
        for t in p.tables
    }
    for expected in (
        "DatabaseEnvironment",
        "Query",
        "Execute",
        "Execute Procedure",
        "Execute Procedure Expect Exception",
    ):
        assert expected in all_fixtures, f"Fixture {expected!r} not found in KBGSuite"
