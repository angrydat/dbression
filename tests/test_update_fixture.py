"""Update fixture tests against in-memory SQLite (no DB setup needed).

DBFit convention recap:
  - Header ending in `=`  → SET column ("set this to whatever")
  - Bare header           → WHERE column (lookup criterion)
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

from dbression.fixtures import resolve_fixture
from dbression.fixtures.base import FixtureContext
from dbression.parser.ast import Table
from dbression.symbols import SymbolTable


@pytest.fixture
def conn():
    eng = create_engine("sqlite:///:memory:")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE kunde (id INTEGER PRIMARY KEY, name TEXT, ort TEXT)"))
        c.execute(
            text(
                "INSERT INTO kunde (id, name, ort) VALUES "
                "(1, 'Anna', 'Wien'), "
                "(2, 'Bob', 'Linz'), "
                "(3, 'Carla', 'Wien')"
            )
        )
    with eng.connect() as c:
        yield c
    eng.dispose()


def _run_update(conn, args: list[str], headers: list[str], rows: list[list[str]]):
    cls = resolve_fixture("Update")
    assert cls is not None
    tbl = Table(name="Update", header_args=args, headers=headers, rows=rows)
    ctx = FixtureContext(conn=conn, symbols=SymbolTable(), stored={})
    return cls().run(tbl, ctx), ctx


def test_update_set_one_column_where_id(conn) -> None:
    res, _ = _run_update(
        conn,
        args=["kunde"],
        headers=["ort=", "id"],  # SET ort, WHERE id
        rows=[["Salzburg", "1"]],
    )
    assert res.passed, res.message
    assert "1 rows" in res.message
    row = conn.execute(text("SELECT ort FROM kunde WHERE id = 1")).one()
    assert row[0] == "Salzburg"


def test_update_multi_set_multi_where(conn) -> None:
    res, _ = _run_update(
        conn,
        args=["kunde"],
        headers=["name=", "ort=", "id"],
        rows=[["BobNeu", "Graz", "2"]],
    )
    assert res.passed
    row = conn.execute(text("SELECT name, ort FROM kunde WHERE id = 2")).one()
    assert row == ("BobNeu", "Graz")


def test_update_multiple_rows_each_with_own_where(conn) -> None:
    res, _ = _run_update(
        conn,
        args=["kunde"],
        headers=["ort=", "id"],
        rows=[["Graz", "1"], ["Innsbruck", "3"]],
    )
    assert res.passed
    assert "2 rows" in res.message
    rows = conn.execute(text("SELECT id, ort FROM kunde ORDER BY id")).all()
    assert rows == [(1, "Graz"), (2, "Linz"), (3, "Innsbruck")]


def test_update_with_symbol_substitution(conn) -> None:
    cls = resolve_fixture("Update")
    ctx = FixtureContext(conn=conn, symbols=SymbolTable(), stored={})
    ctx.symbols.set("target_id", 2)
    ctx.symbols.set("new_ort", "Salzburg")
    tbl = Table(
        name="Update",
        header_args=["kunde"],
        headers=["ort=", "id"],
        rows=[["<<new_ort", "<<target_id"]],
    )
    res = cls().run(tbl, ctx)
    assert res.passed
    row = conn.execute(text("SELECT ort FROM kunde WHERE id = 2")).one()
    assert row[0] == "Salzburg"


def test_update_null_in_where_uses_is_null(conn) -> None:
    """A NULL value in a WHERE column must generate `IS NULL`, not `= NULL`."""
    conn.execute(text("INSERT INTO kunde (id, name, ort) VALUES (4, 'NoOrt', NULL)"))
    res, _ = _run_update(
        conn,
        args=["kunde"],
        headers=["name=", "ort"],
        rows=[["Found", "null"]],
    )
    assert res.passed
    row = conn.execute(text("SELECT name FROM kunde WHERE id = 4")).one()
    assert row[0] == "Found"


def test_update_no_set_columns_fails_gracefully(conn) -> None:
    res, _ = _run_update(
        conn,
        args=["kunde"],
        headers=["id", "name"],  # no `=` anywhere → no SET columns
        rows=[["1", "Anna"]],
    )
    assert not res.passed
    assert "no SET columns" in res.message


def test_update_without_table_name_fails(conn) -> None:
    res, _ = _run_update(conn, args=[], headers=["x="], rows=[["1"]])
    assert not res.passed
    assert "table name" in res.message
