from __future__ import annotations

import pytest

from dbression.symbols import SymbolTable, bind_values, extract_binds, substitute_cell


def test_set_get_has() -> None:
    s = SymbolTable()
    assert not s.has("x")
    s.set("x", 42)
    assert s.has("x")
    assert s.get("x") == 42


def test_get_missing_raises() -> None:
    s = SymbolTable()
    with pytest.raises(KeyError):
        s.get("nope")


def test_substitute_cell_single_symbol() -> None:
    s = SymbolTable()
    s.set("id", 4711)
    assert substitute_cell("<<id", s) == "4711"


def test_substitute_cell_unknown_raises() -> None:
    s = SymbolTable()
    with pytest.raises(KeyError):
        substitute_cell("<<missing", s)


def test_extract_binds_basic() -> None:
    sql = "select * from t where a = :foo and b = :bar"
    assert extract_binds(sql) == ["foo", "bar"]


def test_extract_binds_dedup_order() -> None:
    sql = "update t set a = :v, b = :v where id = :id"
    assert extract_binds(sql) == ["v", "id"]


def test_extract_binds_ignores_quoted_literals() -> None:
    sql = "select ':not_a_bind' from dual where x = :real"
    assert extract_binds(sql) == ["real"]


def test_extract_binds_ignores_oracle_qquote() -> None:
    sql = "select q'~:not_a_bind~' from dual where x = :real"
    assert extract_binds(sql) == ["real"]


def test_bind_values_pulls_from_symbols() -> None:
    s = SymbolTable()
    s.set("id", 1)
    s.set("name", "alice")
    assert bind_values(["id", "name"], s) == {"id": 1, "name": "alice"}
