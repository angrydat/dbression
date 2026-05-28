"""Live tests against the WLK Postgres instance via SQLAlchemy."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from dbression.db import DBError, load_connection_properties, make_engine, wrap_dbapi_error

PROPS = Path.home() / "devel" / "wlk-postgis" / "test" / "connection.properties"

pytestmark = pytest.mark.skipif(
    not PROPS.is_file(), reason="WLK connection.properties not available"
)


@pytest.fixture
def engine():
    cfg = load_connection_properties(PROPS)
    eng = make_engine("postgres", cfg)
    yield eng
    eng.dispose()


def test_select_one(engine) -> None:
    with engine.connect() as conn:
        r = conn.execute(text("select 1 as n")).all()
    assert r == [(1,)]


def test_string_literal(engine) -> None:
    with engine.connect() as conn:
        r = conn.execute(text("select 'OK' as connection")).all()
    assert r == [("OK",)]


def test_native_bind(engine) -> None:
    """SQLAlchemy supports `:name` binds natively without rewriting."""
    with engine.connect() as conn:
        r = conn.execute(text("select cast(:x as int) as v"), {"x": 42}).all()
    assert r == [(42,)]


def test_error_extraction(engine) -> None:
    with engine.connect() as conn:
        with pytest.raises(DBAPIError) as exc_info:
            conn.execute(text("select 1/0"))
    wrapped = wrap_dbapi_error(exc_info.value)
    assert isinstance(wrapped, DBError)
    assert wrapped.sqlstate == "22012"  # division_by_zero
