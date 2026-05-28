"""Phase-2 fixtures: Inspect Table/View/Procedure + Store Query/Compare Stored Queries.

DBFit conventions (best-effort reimplementation, since our existing suites do not use
these fixtures yet — validation will follow whenever someone actually does):

* ``Inspect Table | <schema.tablename>``    → returns (column_name, data_type) rows
* ``Inspect View  | <schema.viewname>``     → like Inspect Table
* ``Inspect Procedure | <schema.procname>`` → (param_name, data_type, direction)
* ``Store Query  | <sql> | <name>``         → runs SQL, stashes (columns, rows) as `name`
* ``Compare Stored Queries | <a> | <b>``    → compares two stashes, fails on diff
"""
from __future__ import annotations

from io import StringIO
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from dbression.db.errors import wrap_dbapi_error
from dbression.fixtures.base import (
    Fixture,
    FixtureContext,
    FixtureResult,
    StoredQuery,
    register,
)
from dbression.parser.ast import Table
from dbression.symbols import substitute_sql_text


# ─────────────────────────────────────────────────────────────────────────────
# Inspect fixtures
# ─────────────────────────────────────────────────────────────────────────────


@register("Inspect Table")
class InspectTable(Fixture):
    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:
        return _inspect_columns(table, ctx, kind="table")


@register("Inspect View")
class InspectView(Fixture):
    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:
        return _inspect_columns(table, ctx, kind="view")


@register("Inspect Procedure")
class InspectProcedure(Fixture):
    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:
        target = table.header_args[0] if table.header_args else ""
        if not target:
            return FixtureResult(passed=False, message="Inspect Procedure without name")
        schema, name = _split_schema(target)
        dialect = ctx.conn.engine.dialect.name
        sql, binds = _inspect_procedure_sql(dialect, schema, name)
        return _run_inspect(table, ctx, sql, binds, kind="procedure")


# ─────────────────────────────────────────────────────────────────────────────
# Store Query / Compare Stored Queries
# ─────────────────────────────────────────────────────────────────────────────


@register("Store Query")
class StoreQueryFixture(Fixture):
    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:
        if len(table.header_args) < 2:
            return FixtureResult(
                passed=False,
                message="Store Query requires SQL + stash name",
            )
        raw_sql, stash_name = table.header_args[0], table.header_args[1].strip()
        sql = substitute_sql_text(raw_sql, ctx.symbols)
        binds = ctx.symbols.as_dict()
        try:
            result = ctx.conn.execute(text(sql), binds)
            columns = list(result.keys())
            rows = [tuple(r) for r in result.fetchall()]
        except DBAPIError as e:
            err = wrap_dbapi_error(e, sql=sql, binds=binds)
            return FixtureResult(
                passed=False,
                message=f"Store Query fail: {err}",
                details=f"SQL:\n{sql}\n\nError: {err}",
            )
        ctx.stored[stash_name] = StoredQuery(columns=columns, rows=rows)
        return FixtureResult(
            passed=True, message=f"Stored {len(rows)} rows as {stash_name!r}"
        )


@register("Compare Stored Queries")
class CompareStoredQueries(Fixture):
    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:
        if len(table.header_args) < 2:
            return FixtureResult(
                passed=False,
                message="Compare Stored Queries requires two stash names",
            )
        a_name, b_name = table.header_args[0].strip(), table.header_args[1].strip()
        if a_name not in ctx.stored:
            return FixtureResult(passed=False, message=f"Stash not found: {a_name!r}")
        if b_name not in ctx.stored:
            return FixtureResult(passed=False, message=f"Stash not found: {b_name!r}")
        a, b = ctx.stored[a_name], ctx.stored[b_name]
        if a.columns != b.columns:
            return _stash_diff(a_name, a, b_name, b, "Columns differ")
        # Ordered comparison; a future flag like `--unordered` could be added.
        if a.rows != b.rows:
            return _stash_diff(a_name, a, b_name, b, "Row content differs")
        return FixtureResult(
            passed=True, message=f"Stored Queries {a_name} ≡ {b_name} ({len(a.rows)} rows)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _split_schema(qualified: str) -> tuple[str | None, str]:
    """Split ``schema.table`` or bracketed identifier ``[schema].[table]``.

    Currently unsupported: quoted identifiers containing dots in the name — we'll handle
    those when somebody actually uses them.
    """
    s = qualified.strip().replace("[", "").replace("]", "").replace('"', "")
    if "." in s:
        sch, _, name = s.partition(".")
        return sch.strip() or None, name.strip()
    return None, s


def _inspect_columns_sql(dialect: str, schema: str | None, name: str) -> tuple[str, dict[str, Any]]:
    """Dialect-specific SQL for an ``information_schema.columns`` lookup."""
    if dialect == "oracle":
        sql = (
            "SELECT column_name, data_type FROM all_tab_columns "
            "WHERE table_name = :name"
            + (" AND owner = :schema" if schema else "")
            + " ORDER BY column_id"
        )
        binds: dict[str, Any] = {"name": name.upper()}
        if schema:
            binds["schema"] = schema.upper()
        return sql, binds
    # PG + MSSQL: standard information_schema
    where = ["table_name = :name"]
    binds = {"name": name}
    if schema:
        where.append("table_schema = :schema")
        binds["schema"] = schema
    sql = (
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE " + " AND ".join(where) + " ORDER BY ordinal_position"
    )
    return sql, binds


def _inspect_procedure_sql(
    dialect: str, schema: str | None, name: str
) -> tuple[str, dict[str, Any]]:
    if dialect == "oracle":
        sql = (
            "SELECT argument_name AS param_name, data_type, in_out AS direction "
            "FROM all_arguments WHERE object_name = :name"
            + (" AND owner = :schema" if schema else "")
            + " ORDER BY position"
        )
        binds: dict[str, Any] = {"name": name.upper()}
        if schema:
            binds["schema"] = schema.upper()
        return sql, binds
    # PG + MSSQL: information_schema.parameters (PG maps procedures via routines)
    where = ["specific_name LIKE :name_pat"]
    binds = {"name_pat": f"{name}%"}
    if schema:
        where.append("specific_schema = :schema")
        binds["schema"] = schema
    sql = (
        "SELECT parameter_name AS param_name, data_type, parameter_mode AS direction "
        "FROM information_schema.parameters WHERE "
        + " AND ".join(where)
        + " ORDER BY ordinal_position"
    )
    return sql, binds


def _inspect_columns(table: Table, ctx: FixtureContext, kind: str) -> FixtureResult:
    target = table.header_args[0] if table.header_args else ""
    if not target:
        return FixtureResult(passed=False, message=f"Inspect {kind.title()} without name")
    schema, name = _split_schema(target)
    dialect = ctx.conn.engine.dialect.name
    sql, binds = _inspect_columns_sql(dialect, schema, name)
    return _run_inspect(table, ctx, sql, binds, kind=kind)


def _run_inspect(
    table: Table,
    ctx: FixtureContext,
    sql: str,
    binds: dict[str, Any],
    kind: str,
) -> FixtureResult:
    try:
        result = ctx.conn.execute(text(sql), binds)
        cols = list(result.keys())
        rows = [tuple(r) for r in result.fetchall()]
    except DBAPIError as e:
        err = wrap_dbapi_error(e, sql=sql, binds=binds)
        return FixtureResult(
            passed=False,
            message=f"Inspect {kind.title()} fail: {err}",
            details=f"SQL:\n{sql}\n\nError: {err}",
        )
    if not rows:
        return FixtureResult(
            passed=False,
            message=f"{kind.title()} has no columns/parameters (or does not exist)",
            details=f"SQL:\n{sql}\nBinds: {binds}",
        )
    # If the user provided expected body rows we compare; otherwise just report
    # informatively (passed=True).
    if not table.headers or not table.rows:
        return FixtureResult(
            passed=True,
            message=f"Inspect {kind.title()}: {len(rows)} entries",
            details=_format_inspect_rows(cols, rows),
        )
    # Body compare: expected headers must be a subset of the actual ones.
    col_idx = {c.lower(): i for i, c in enumerate(cols)}
    expected_idx: list[int] = []
    for h in table.headers:
        h_norm = h.strip().rstrip("?").lower()
        if h_norm not in col_idx:
            return FixtureResult(
                passed=False,
                message=f"Header {h!r} not present in inspect result",
                details=f"Available columns: {cols}",
            )
        expected_idx.append(col_idx[h_norm])
    # Row-by-row comparison (case-insensitive, trimmed).
    if len(rows) != len(table.rows):
        return FixtureResult(
            passed=False,
            message=f"Count mismatch: expected {len(table.rows)}, got {len(rows)}",
            details=_format_inspect_rows(cols, rows),
        )
    for exp_row, db_row in zip(table.rows, rows):
        for c_i, exp_val in enumerate(exp_row):
            db_val = db_row[expected_idx[c_i]] if c_i < len(expected_idx) else None
            exp_norm = (exp_val or "").strip().lower()
            db_norm = "" if db_val is None else str(db_val).strip().lower()
            if exp_norm != db_norm:
                return FixtureResult(
                    passed=False,
                    message="Inspect mismatch",
                    details=_format_inspect_rows(cols, rows),
                )
    return FixtureResult(
        passed=True,
        message=f"Inspect {kind.title()} OK ({len(rows)} entries)",
    )


def _format_inspect_rows(cols: list[str], rows: list[tuple]) -> str:
    buf = StringIO()
    buf.write("| " + " | ".join(cols) + " |\n")
    for r in rows:
        buf.write("| " + " | ".join("null" if v is None else str(v) for v in r) + " |\n")
    return buf.getvalue()


def _stash_diff(
    a_name: str, a: StoredQuery, b_name: str, b: StoredQuery, headline: str
) -> FixtureResult:
    buf = StringIO()
    buf.write(f"{headline}\n\n")
    buf.write(f"{a_name} ({len(a.rows)} rows, cols={a.columns}):\n")
    for r in a.rows[:5]:
        buf.write(f"  {r}\n")
    if len(a.rows) > 5:
        buf.write(f"  ... ({len(a.rows) - 5} more)\n")
    buf.write(f"\n{b_name} ({len(b.rows)} rows, cols={b.columns}):\n")
    for r in b.rows[:5]:
        buf.write(f"  {r}\n")
    if len(b.rows) > 5:
        buf.write(f"  ... ({len(b.rows) - 5} more)\n")
    return FixtureResult(passed=False, message=headline, details=buf.getvalue())
