"""Roundtrip tests: .wiki → .test.md → AST should be structurally equivalent."""
from __future__ import annotations

from pathlib import Path

import pytest

from dbression.parser.markdown import parse_markdown
from dbression.parser.markdown_writer import page_to_markdown
from dbression.parser.wiki import parse_wiki


def _roundtrip(tmp_path: Path, wiki_content: str):
    wiki_file = tmp_path / "T.wiki"
    wiki_file.write_text(wiki_content, encoding="utf-8")
    wiki_page = parse_wiki(wiki_file)

    md_file = tmp_path / "T.test.md"
    md_file.write_text(page_to_markdown(wiki_page), encoding="utf-8")
    md_page = parse_markdown(md_file)
    return wiki_page, md_page


def test_roundtrip_query(tmp_path: Path) -> None:
    wp, mp = _roundtrip(
        tmp_path,
        "!|Query|select 1 as n|\n|n|\n|1|\n",
    )
    assert [t.name for t in mp.tables] == [t.name for t in wp.tables] == ["Query"]
    assert mp.tables[0].header_args == wp.tables[0].header_args
    assert mp.tables[0].headers == wp.tables[0].headers
    assert mp.tables[0].rows == wp.tables[0].rows


def test_roundtrip_insert_with_substitution(tmp_path: Path) -> None:
    wp, mp = _roundtrip(
        tmp_path,
        "!|Insert|wlk.org_benutzer|\n"
        "|wlv_user|kompetenz|\n"
        "|dbfit|<<k|\n"
        "|alice|<<k|\n",
    )
    assert mp.tables[0].name == "Insert"
    assert mp.tables[0].header_args == ["wlk.org_benutzer"]
    assert mp.tables[0].rows == [["dbfit", "<<k"], ["alice", "<<k"]]


def test_roundtrip_execute_procedure_expect_exception(tmp_path: Path) -> None:
    wp, mp = _roundtrip(
        tmp_path,
        "!|Execute Procedure Expect Exception|pr_set_status|23505|\n"
        "|pBenutzer|pStatus|pOid|\n"
        "|dbfit|Bearbeitung|<<id|\n",
    )
    assert mp.tables[0].name == "Execute Procedure Expect Exception"
    assert mp.tables[0].header_args == ["pr_set_status", "23505"]
    assert mp.tables[0].rows == [["dbfit", "Bearbeitung", "<<id"]]


def test_roundtrip_engine_directives(tmp_path: Path) -> None:
    wp, mp = _roundtrip(
        tmp_path,
        "!|DatabaseEnvironment|postgres|\n"
        "\n"
        "!|ConnectUsingFile|/x/conn.properties|\n",
    )
    md_fixtures = [t.name for t in mp.tables]
    assert "DatabaseEnvironment" in md_fixtures
    assert "ConnectUsingFile" in md_fixtures
    env = next(t for t in mp.tables if t.name == "DatabaseEnvironment")
    cu = next(t for t in mp.tables if t.name == "ConnectUsingFile")
    assert env.header_args == ["postgres"]
    assert cu.header_args == ["/x/conn.properties"]


KBG_FILE = Path.home() / "devel" / "ma31-ora" / "test" / "KBGSuite" / "ANetzTopologieTest.wiki"


@pytest.mark.skipif(not KBG_FILE.is_file(), reason="KBGSuite test file not available")
def test_roundtrip_real_kbg_file(tmp_path: Path) -> None:
    """Smoke against a real KBG wiki file (more complex structures)."""
    wp = parse_wiki(KBG_FILE)
    md_text = page_to_markdown(wp)
    out = tmp_path / "T.test.md"
    out.write_text(md_text, encoding="utf-8")
    mp = parse_markdown(out)
    # Number + names of the fixture tables should match
    assert [t.name for t in mp.tables] == [t.name for t in wp.tables]
    # The first Query's header_args (SQL) should be unchanged
    first_query_wiki = next(t for t in wp.tables if t.name == "Query")
    first_query_md = next(t for t in mp.tables if t.name == "Query")
    assert first_query_md.header_args[0].strip() == first_query_wiki.header_args[0].strip()
