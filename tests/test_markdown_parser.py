from __future__ import annotations

from pathlib import Path

from dbression.parser import parse_suite
from dbression.parser.markdown import parse_markdown


def test_simple_query(tmp_path: Path) -> None:
    src = tmp_path / "T.test.md"
    src.write_text(
        "# My Test\n"
        "\n"
        "### Query\n"
        "\n"
        "```sql\n"
        "select 1 as n\n"
        "```\n"
        "\n"
        "| n |\n"
        "|---|\n"
        "| 1 |\n",
        encoding="utf-8",
    )
    page = parse_markdown(src)
    assert page.name == "T"
    assert len(page.tables) == 1
    tbl = page.tables[0]
    assert tbl.name == "Query"
    assert tbl.header_args == ["select 1 as n"]
    assert tbl.headers == ["n"]
    assert tbl.rows == [["1"]]


def test_insert_with_args_and_table(tmp_path: Path) -> None:
    src = tmp_path / "T.test.md"
    src.write_text(
        "### Insert wlk.org_benutzer\n"
        "\n"
        "| wlv_user | kompetenz |\n"
        "|----------|-----------|\n"
        "| dbfit    | 62        |\n",
        encoding="utf-8",
    )
    tbl = parse_markdown(src).tables[0]
    assert tbl.name == "Insert"
    assert tbl.header_args == ["wlk.org_benutzer"]
    assert tbl.headers == ["wlv_user", "kompetenz"]
    assert tbl.rows == [["dbfit", "62"]]


def test_execute_procedure_expect_exception_with_code(tmp_path: Path) -> None:
    src = tmp_path / "T.test.md"
    src.write_text(
        "### Execute Procedure Expect Exception pr_set_status 23505\n"
        "\n"
        "| pBenutzer | pStatus     | pOid |\n"
        "|-----------|-------------|------|\n"
        "| dbfit     | Bearbeitung | <<id |\n",
        encoding="utf-8",
    )
    tbl = parse_markdown(src).tables[0]
    assert tbl.name == "Execute Procedure Expect Exception"
    assert tbl.header_args == ["pr_set_status", "23505"]
    assert tbl.rows == [["dbfit", "Bearbeitung", "<<id"]]


def test_html_comment_directives(tmp_path: Path) -> None:
    src = tmp_path / "_root.test.md"
    src.write_text(
        "# Root\n"
        "\n"
        "<!-- dbression:env=postgres -->\n"
        "<!-- dbression:connection=conn.properties -->\n"
        "<!-- dbression:tags critical, NotOnCI -->\n",
        encoding="utf-8",
    )
    page = parse_markdown(src)
    assert page.tags == ["critical", "NotOnCI"]
    fixtures = [t.name for t in page.tables]
    assert "DatabaseEnvironment" in fixtures
    assert "ConnectUsingFile" in fixtures
    env_table = next(t for t in page.tables if t.name == "DatabaseEnvironment")
    assert env_table.header_args == ["postgres"]


def test_capture_in_md_table(tmp_path: Path) -> None:
    src = tmp_path / "T.test.md"
    src.write_text(
        "### Query\n"
        "\n"
        "```sql\n"
        "select id from foo\n"
        "```\n"
        "\n"
        "| id     |\n"
        "|--------|\n"
        "| >>x_id |\n",
        encoding="utf-8",
    )
    tbl = parse_markdown(src).tables[0]
    assert tbl.rows == [[">>x_id"]]


def test_suite_discovers_md_format(tmp_path: Path) -> None:
    (tmp_path / "_root.test.md").write_text(
        "<!-- dbression:env=postgres -->\n<!-- dbression:connection=c.properties -->\n",
        encoding="utf-8",
    )
    (tmp_path / "Foo.test.md").write_text(
        "### Query\n```sql\nselect 1\n```\n| n |\n|---|\n| 1 |\n",
        encoding="utf-8",
    )
    suite = parse_suite(tmp_path)
    assert suite.root_page is not None
    assert suite.root_page.name == "_root"
    assert [p.name for p in suite.pages] == ["Foo"]


def test_md_wins_over_wiki(tmp_path: Path) -> None:
    """When both formats exist for the same page name: Markdown wins."""
    (tmp_path / "_root.test.md").write_text(
        "<!-- dbression:env=postgres -->\n<!-- dbression:connection=c.properties -->\n",
        encoding="utf-8",
    )
    (tmp_path / "Same.wiki").write_text("!|Query|select 'wiki'|\n|c|\n|wiki|\n", encoding="utf-8")
    (tmp_path / "Same.test.md").write_text(
        "### Query\n```sql\nselect 'md'\n```\n| c |\n|---|\n| md |\n",
        encoding="utf-8",
    )
    suite = parse_suite(tmp_path)
    same = next(p for p in suite.pages if p.name == "Same")
    assert same.tables[0].header_args == ["select 'md'"]
