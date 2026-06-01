"""SQLite engine smoke test — confirm the DatabaseEnvironment dispatch and end-to-end
Query / Execute against an in-memory SQLite DB."""
from __future__ import annotations

from sqlalchemy import text

from dbression.db.connection import ConnectionConfig
from dbression.db.engine import make_engine
from dbression.fixtures import resolve_fixture
from dbression.fixtures.base import FixtureContext
from dbression.parser.ast import Table
from dbression.symbols import SymbolTable


def _ctx(conn):
    return FixtureContext(conn=conn, symbols=SymbolTable(), stored={})


def test_sqlite_memory_via_database_environment():
    cfg = ConnectionConfig(service=":memory:")
    eng = make_engine("sqlite", cfg)
    with eng.connect() as c:
        assert c.execute(text("select 1")).scalar() == 1


def test_sqlite_file_path_url_shape(tmp_path):
    db = tmp_path / "x.db"
    cfg = ConnectionConfig(service=str(db))
    eng = make_engine("sqlite", cfg)
    # Absolute path → 4 slashes
    assert str(eng.url).startswith("sqlite:////")
    with eng.connect() as c:
        c.execute(text("create table t (a int)"))
        c.execute(text("insert into t values (42)"))
        assert c.execute(text("select a from t")).scalar() == 42


def test_sqlite_runs_query_fixture():
    cfg = ConnectionConfig(service=":memory:")
    eng = make_engine("sqlite", cfg)
    with eng.begin() as conn:
        conn.execute(text("create table t (n int, name text)"))
        conn.execute(text("insert into t values (1, 'a'), (2, 'b')"))
    with eng.connect() as conn:
        cls = resolve_fixture("Query")
        tbl = Table(
            name="Query",
            header_args=["select n, name from t order by n"],
            headers=["n", "name"],
            rows=[["1", "a"], ["2", "b"]],
        )
        res = cls().run(tbl, _ctx(conn))
        assert res.passed, res.message


def test_sqlite_alias_sqlite3_also_works():
    cfg = ConnectionConfig(service=":memory:")
    eng = make_engine("sqlite3", cfg)
    with eng.connect() as c:
        assert c.execute(text("select 1")).scalar() == 1
