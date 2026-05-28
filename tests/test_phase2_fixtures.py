"""Tests for the Phase-2 fixtures (Inspect + Store/Compare Query).

Structural tests against in-memory SQLite, so no DB setup is required.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from dbression.fixtures import REGISTRY, resolve_fixture
from dbression.fixtures.base import FixtureContext, StoredQuery
from dbression.parser.ast import Table
from dbression.symbols import SymbolTable


@pytest.fixture
def conn():
    eng = create_engine("sqlite:///:memory:")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE foo (id INTEGER, name TEXT)"))
        c.execute(text("INSERT INTO foo VALUES (1, 'a'), (2, 'b'), (3, 'c')"))
    with eng.connect() as c:
        yield c
    eng.dispose()


def _ctx(conn) -> FixtureContext:
    return FixtureContext(conn=conn, symbols=SymbolTable(), stored={})


def test_store_query_stashes_result(conn) -> None:
    cls = resolve_fixture("Store Query")
    assert cls is not None
    tbl = Table(name="Store Query", header_args=["SELECT id, name FROM foo ORDER BY id", "baseline"])
    ctx = _ctx(conn)
    res = cls().run(tbl, ctx)
    assert res.passed
    assert "baseline" in ctx.stored
    assert ctx.stored["baseline"].columns == ["id", "name"]
    assert ctx.stored["baseline"].rows == [(1, "a"), (2, "b"), (3, "c")]


def test_compare_stored_queries_equal(conn) -> None:
    cls_store = resolve_fixture("Store Query")
    cls_cmp = resolve_fixture("Compare Stored Queries")
    assert cls_store is not None and cls_cmp is not None
    ctx = _ctx(conn)
    cls_store().run(Table(name="Store Query", header_args=["SELECT id FROM foo", "a"]), ctx)
    cls_store().run(Table(name="Store Query", header_args=["SELECT id FROM foo", "b"]), ctx)
    res = cls_cmp().run(Table(name="Compare Stored Queries", header_args=["a", "b"]), ctx)
    assert res.passed


def test_compare_stored_queries_diff(conn) -> None:
    cls_store = resolve_fixture("Store Query")
    cls_cmp = resolve_fixture("Compare Stored Queries")
    ctx = _ctx(conn)
    cls_store().run(Table(name="Store Query", header_args=["SELECT id FROM foo WHERE id < 2", "a"]), ctx)
    cls_store().run(Table(name="Store Query", header_args=["SELECT id FROM foo WHERE id > 1", "b"]), ctx)
    res = cls_cmp().run(Table(name="Compare Stored Queries", header_args=["a", "b"]), ctx)
    assert not res.passed
    assert "Row content" in res.message


def test_compare_missing_stash(conn) -> None:
    cls_cmp = resolve_fixture("Compare Stored Queries")
    res = cls_cmp().run(Table(name="Compare Stored Queries", header_args=["a", "b"]), _ctx(conn))
    assert not res.passed
    assert "not found" in res.message


def test_inspect_fixtures_registered() -> None:
    """Inspect fixtures must be in the registry."""
    for fname in ("Inspect Table", "Inspect View", "Inspect Procedure"):
        assert resolve_fixture(fname) is not None, f"{fname} missing from REGISTRY"


WLK_PROPS = Path.home() / "devel" / "wlk-postgis" / "test" / "connection.properties"


@pytest.mark.skipif(not WLK_PROPS.is_file(), reason="WLK PG not available")
def test_inspect_table_live_wlk() -> None:
    """Live smoke: Inspect Table against a known WLK table."""
    from dbression.db import load_connection_properties, make_engine

    cfg = load_connection_properties(WLK_PROPS)
    eng = make_engine("postgres", cfg)
    try:
        with eng.connect() as c:
            cls = resolve_fixture("Inspect Table")
            tbl = Table(name="Inspect Table", header_args=["wlk.org_benutzer"])
            res = cls().run(tbl, FixtureContext(conn=c, symbols=SymbolTable(), stored={}))
            assert res.passed, f"Inspect Table failed: {res.message}\n{res.details}"
            assert "wlv_user" in res.details.lower()
            assert "kompetenz" in res.details.lower()
    finally:
        eng.dispose()
