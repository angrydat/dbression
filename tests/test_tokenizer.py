from __future__ import annotations

from dbression.parser.tokenizer import DirectiveToken, Heading, TableRow, tokenize


def _tokens(text: str) -> list:
    return list(tokenize(text))


def test_empty_input() -> None:
    assert _tokens("") == []
    assert _tokens("\n\n\n") == []


def test_simple_directive() -> None:
    toks = _tokens("!path lib/*.jar")
    assert len(toks) == 1
    assert isinstance(toks[0], DirectiveToken)
    assert toks[0].name == "path"
    assert toks[0].value == "lib/*.jar"


def test_heading_levels() -> None:
    toks = _tokens("!1 Title\n!3 Section")
    assert [t.level for t in toks if isinstance(t, Heading)] == [1, 3]
    assert [t.text for t in toks if isinstance(t, Heading)] == ["Title", "Section"]


def test_contents_widget_ignored() -> None:
    assert _tokens("!contents -R2 -g -p -f -h") == []


def test_table_starts_with_bang_pipe() -> None:
    toks = _tokens("!|Query|select 1 from dual|\n|RESULT|\n|1|")
    assert len(toks) == 3
    assert isinstance(toks[0], TableRow)
    assert toks[0].starts_table is True
    assert toks[0].cells == ["Query", "select 1 from dual"]
    assert toks[1].starts_table is False
    assert toks[1].cells == ["RESULT"]
    assert toks[2].cells == ["1"]


def test_escape_block_preserves_pipes_and_newlines() -> None:
    text = (
        "!|Query|!-\n"
        "  select a, b from t\n"
        "  where x != 0\n"
        "-!|\n"
        "|A|B|\n"
        "|1|2|"
    )
    toks = _tokens(text)
    # The first token is the table header row; the escape cell must hold the multi-line SQL.
    assert isinstance(toks[0], TableRow)
    assert toks[0].cells[0] == "Query"
    sql = toks[0].cells[1]
    assert "select a, b from t" in sql
    assert "where x != 0" in sql
    # Follow-up rows are recognized correctly
    assert toks[1].cells == ["A", "B"]
    assert toks[2].cells == ["1", "2"]


def test_oracle_quote_protects_pipes() -> None:
    toks = _tokens("!|Execute|begin execute immediate q'~create or replace |xyz| as~'; end;|")
    assert isinstance(toks[0], TableRow)
    # Two cells: fixture name + statement; the inner `|xyz|` must NOT split.
    assert toks[0].cells[0] == "Execute"
    assert "q'~create or replace |xyz| as~'" in toks[0].cells[1]


def test_import_fixture_table() -> None:
    toks = _tokens("!|import fixture|\n|dbfit.fixture|")
    assert len(toks) == 2
    assert toks[0].starts_table is True
    assert toks[0].cells == ["import fixture"]
    assert toks[1].starts_table is False
    assert toks[1].cells == ["dbfit.fixture"]
