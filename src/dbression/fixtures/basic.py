"""Phase-1 MVP fixtures: Execute, Query, Insert, Delete, Set Parameter,
Execute Procedure (+ Expect Exception), runtime DatabaseEnvironment."""
from __future__ import annotations

from io import StringIO
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from dbression.db.errors import wrap_dbapi_error
from dbression.fixtures.base import Fixture, FixtureContext, FixtureResult, register
from dbression.parser.ast import Table
from dbression.symbols import substitute_cell, substitute_sql_text


@register("Execute Ddl")
@register("Execute")
class Execute(Fixture):
    """Execute a SQL/PL-SQL statement from the table header.

    Expects the form ``!|Execute|<sql>|``. Data rows, if any, are ignored. On error the
    DB exception is passed through into the result details.
    """

    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:
        raw_sql = table.header_args[0] if table.header_args else ""
        if not raw_sql.strip():
            return FixtureResult(passed=False, message="Execute without SQL")
        sql = substitute_sql_text(raw_sql, ctx.symbols)
        binds = ctx.symbols.as_dict()
        try:
            ctx.conn.execute(text(sql), binds)
            return FixtureResult(passed=True, message="Execute OK")
        except DBAPIError as e:
            err = wrap_dbapi_error(e, sql=sql, binds=binds)
            return FixtureResult(
                passed=False, message=f"Execute fail: {err}", details=_format_sql_block(sql, err)
            )


@register("Query")
class Query(Fixture):
    """SELECT with expected result rows.

    The second table row is the column header — column names with a ``>>name`` prefix
    capture the value into the symbol ``name``. Following rows are expected values.
    Comparison is exact (order, count, string representation). ``null`` is interpreted
    as NULL/None.
    """

    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:
        raw_sql = table.header_args[0] if table.header_args else ""
        if not raw_sql.strip():
            return FixtureResult(passed=False, message="Query without SQL")
        sql = substitute_sql_text(raw_sql, ctx.symbols)
        binds = ctx.symbols.as_dict()
        try:
            result = ctx.conn.execute(text(sql), binds)
            cols = list(result.keys())
            rows = [tuple(r) for r in result.fetchall()]
        except DBAPIError as e:
            err = wrap_dbapi_error(e, sql=sql, binds=binds)
            return FixtureResult(
                passed=False, message=f"Query fail: {err}", details=_format_sql_block(sql, err)
            )

        # Header handling: an empty table (only the fixture header, no data rows) means
        # "expect an empty result". Otherwise compare headers + rows.
        if not table.headers:
            if rows:
                return _row_mismatch(sql, [], [], cols, rows)
            return FixtureResult(passed=True, message="Query OK (0 rows)")

        # Normalize headers: a `?` suffix marks an "output column" in DBFit — for us a
        # no-op, since we read all columns from the result anyway.
        expected_headers = [h[:-1].strip() if h.endswith("?") else h.strip() for h in table.headers]
        expected_rows = table.rows

        if len(rows) != len(expected_rows):
            return _row_mismatch(sql, expected_headers, expected_rows, cols, rows)

        # Column mapping: expected header name → index in the DB result (case-insensitive)
        col_index: dict[str, int] = {c.lower(): i for i, c in enumerate(cols)}

        # For each data row + data cell:
        #   - Cell starts with ">>name": capture the value of this result column into
        #     symbol `name`.
        #   - Otherwise: literal comparison against the DB value.
        for r_i, (exp_row, db_row) in enumerate(zip(expected_rows, rows)):
            for c_i, exp_val in enumerate(exp_row):
                col_name = expected_headers[c_i] if c_i < len(expected_headers) else ""
                if not col_name:
                    continue
                db_idx = col_index.get(col_name.lower())
                if db_idx is None:
                    return FixtureResult(
                        passed=False,
                        message=f"Column {col_name!r} not in result",
                        details=f"Available columns: {cols}",
                    )
                db_val = db_row[db_idx]
                stripped = exp_val.strip()
                if stripped.startswith(">>"):
                    ctx.symbols.set(stripped[2:], db_val)
                    continue
                # `<<sym` in expected cells: substitute from the symbol table before compare.
                resolved = substitute_cell(stripped, ctx.symbols) if "<<" in stripped else exp_val
                if not _cells_equal(resolved, db_val):
                    return _row_mismatch(sql, expected_headers, expected_rows, cols, rows)

        return FixtureResult(passed=True, message=f"Query OK ({len(rows)} rows)")


@register("Set Parameter")
class SetParameter(Fixture):
    """``!|Set Parameter|name|value|[type]|`` — write a value to the symbol table.

    The optional third argument is a Java type name (e.g. ``java.lang.Integer``) — we
    do best-effort Python type conversion and fall back to string otherwise.
    """

    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:
        args = table.header_args
        if len(args) < 2:
            return FixtureResult(passed=False, message="Set Parameter requires name + value")
        name = args[0].strip()
        raw = args[1].strip()
        type_hint = args[2].strip().lower() if len(args) >= 3 else ""
        value: Any = raw
        try:
            if "int" in type_hint or "long" in type_hint:
                value = int(raw)
            elif "double" in type_hint or "float" in type_hint or "decimal" in type_hint:
                value = float(raw)
        except ValueError:
            pass  # on conversion failure keep raw as a string
        ctx.symbols.set(name, value)
        return FixtureResult(passed=True, message=f"Set Parameter {name}={value!r}")


@register("Update")
class Update(Fixture):
    """Update fixture — Phase-1 stub.

    DBFit's convention here is complex (WHERE columns appended at the end of the row,
    marked via `=` column headers). WLK uses no Update fixtures and KBGSuite only once —
    implementation deferred until a concrete example exists.
    """

    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:
        return FixtureResult(
            passed=False,
            message="Update fixture not implemented yet (Phase 1 MVP)",
        )


@register("Insert")
class Insert(Fixture):
    """``!|Insert|<schema.table>|`` with column headers and data rows.

    Data cell conventions:
    * ``<<sym``      → substitute the value from the symbol table
    * empty/``null`` → NULL
    * otherwise      → literal value

    Column headers prefixed with ``>>sym`` are captured via ``RETURNING`` after the insert
    (Postgres syntax — Oracle would need ``RETURNING … INTO``; we'll address that when
    KBG goes live).
    """

    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:
        tablename = table.header_args[0] if table.header_args else ""
        if not tablename:
            return FixtureResult(passed=False, message="Insert without table name")
        if not table.headers:
            return FixtureResult(passed=False, message="Insert without column headers")

        # `>>sym` in headers marks capture columns — those do NOT go into the INSERT
        # column list; instead we read them back via RETURNING.
        write_cols: list[str] = []
        capture_cols: list[tuple[str, str]] = []  # (column_name, symbol_name)
        for h in table.headers:
            h = h.strip()
            if h.startswith(">>"):
                sym = h[2:]
                capture_cols.append((sym, sym))  # column name == symbol name (DBFit convention)
            else:
                write_cols.append(h)

        if not write_cols:
            return FixtureResult(
                passed=False, message="Insert without writable columns (all are captures)"
            )

        returning = ""
        if capture_cols:
            returning = " RETURNING " + ", ".join(c for c, _ in capture_cols)

        inserted = 0
        for r_i, row in enumerate(table.rows):
            placeholders = []
            binds: dict[str, Any] = {}
            for c_i, col in enumerate(write_cols):
                # Find the cell: write_cols is a subset of headers — access the cell by
                # the column's position in the headers array.
                header_idx = table.headers.index(col) if col in table.headers else c_i
                cell = row[header_idx] if header_idx < len(row) else ""
                key = f"v_{c_i}"
                placeholders.append(f":{key}")
                binds[key] = _cell_to_bind_value(cell, ctx)
            sql = (
                f"INSERT INTO {tablename} ({', '.join(write_cols)}) "
                f"VALUES ({', '.join(placeholders)}){returning}"
            )
            try:
                result = ctx.conn.execute(text(sql), binds)
                if capture_cols and result.returns_rows:
                    returned = result.fetchone()
                    if returned is not None:
                        for i, (_, sym) in enumerate(capture_cols):
                            ctx.symbols.set(sym, returned[i])
                inserted += 1
            except DBAPIError as e:
                err = wrap_dbapi_error(e, sql=sql, binds=binds)
                return FixtureResult(
                    passed=False,
                    message=f"Insert fail at row {r_i + 1}: {err}",
                    details=_format_sql_block(sql, err),
                )

        return FixtureResult(passed=True, message=f"Insert {inserted} rows into {tablename}")


@register("Delete")
class Delete(Fixture):
    """``!|Delete|<schema.table>|`` with column headers + data rows (WHERE clause values).

    Each data row deletes every row whose column values match exactly. WLK uses this in
    some teardowns.
    """

    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:
        tablename = table.header_args[0] if table.header_args else ""
        if not tablename:
            return FixtureResult(passed=False, message="Delete without table name")
        if not table.headers:
            return FixtureResult(passed=False, message="Delete without WHERE columns")

        deleted = 0
        for r_i, row in enumerate(table.rows):
            wheres = []
            binds: dict[str, Any] = {}
            for c_i, col in enumerate(table.headers):
                key = f"w_{c_i}"
                cell = row[c_i] if c_i < len(row) else ""
                val = _cell_to_bind_value(cell, ctx)
                if val is None:
                    wheres.append(f"{col} IS NULL")
                else:
                    wheres.append(f"{col} = :{key}")
                    binds[key] = val
            sql = f"DELETE FROM {tablename} WHERE {' AND '.join(wheres)}"
            try:
                result = ctx.conn.execute(text(sql), binds)
                deleted += result.rowcount or 0
            except DBAPIError as e:
                err = wrap_dbapi_error(e, sql=sql, binds=binds)
                return FixtureResult(
                    passed=False,
                    message=f"Delete fail at row {r_i + 1}: {err}",
                    details=_format_sql_block(sql, err),
                )

        return FixtureResult(passed=True, message=f"Delete {deleted} rows from {tablename}")


@register("Execute Procedure")
class ExecuteProcedure(Fixture):
    """``!|Execute Procedure|<name>|`` plus a header row with parameter names and data rows
    with values.

    For each data row the procedure is invoked once.
    Postgres: ``SELECT <name>(p := :p, …)`` with ``CALL`` as a fallback for actual procedures.
    Oracle:   ``BEGIN <name>(p => :p); END;``.
    SQL Server: ``EXEC <name> @p = :p``.

    Captures (``>>sym`` in a data cell or output header marked with ``?``) for functions
    that return values are not supported in the Phase-1 MVP; this fixture just calls.
    """

    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:
        proc_name = table.header_args[0] if table.header_args else ""
        if not proc_name:
            return FixtureResult(passed=False, message="Execute Procedure without name")

        # No headers/rows: simple parameter-less call.
        if not table.headers:
            return _call_proc(proc_name, [], [], ctx, expect_exception=False)
        param_names = [h.strip().rstrip("?") for h in table.headers]
        for r_i, row in enumerate(table.rows):
            sub = _call_proc(proc_name, param_names, row, ctx, expect_exception=False)
            if not sub.passed:
                return FixtureResult(
                    passed=False,
                    message=f"Execute Procedure fail at row {r_i + 1}: {sub.message}",
                    details=sub.details,
                )
        return FixtureResult(
            passed=True, message=f"Execute Procedure {proc_name} ({len(table.rows)}x)"
        )


@register("Execute Procedure Expect Exception")
class ExecuteProcedureExpectException(Fixture):
    """``!|Execute Procedure Expect Exception|<name>|[code]|`` — expect a DB exception.

    The optional ``code`` (numeric or 5-character SQLSTATE) must match the raised error
    if given. Without ``code`` any exception is sufficient.
    """

    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:
        if not table.header_args:
            return FixtureResult(
                passed=False, message="Execute Procedure Expect Exception without name"
            )
        proc_name = table.header_args[0]
        expected_code = table.header_args[1].strip() if len(table.header_args) >= 2 else ""

        param_names = [h.strip().rstrip("?") for h in table.headers] if table.headers else []
        rows = table.rows if table.rows else [[]]

        for r_i, row in enumerate(rows):
            sub = _call_proc(
                proc_name,
                param_names,
                row,
                ctx,
                expect_exception=True,
                expected_code=expected_code,
            )
            if not sub.passed:
                return FixtureResult(
                    passed=False,
                    message=(
                        f"Execute Procedure Expect Exception fail at row {r_i + 1}: "
                        f"{sub.message}"
                    ),
                    details=sub.details,
                )
        return FixtureResult(
            passed=True,
            message=f"Execute Procedure Expect Exception {proc_name} ({len(rows)}x)",
        )


@register("DatabaseEnvironment")
class _DatabaseEnvironmentRuntime(Fixture):
    """When ``!|DatabaseEnvironment|`` appears as a table without arguments and the data
    row carries a single command like ``rollback``, run that command on the connection.

    Overrides the suite-directive variant from ``suite_fixtures.py`` (last-registered wins).
    """

    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:
        # Suite directive `!|DatabaseEnvironment|oracle|` — no-op (engine is already built).
        if table.header_args:
            return FixtureResult(
                passed=True,
                message=f"DatabaseEnvironment={table.header_args[0]} (runtime no-op)",
            )
        # Runtime command in headers (e.g. ['rollback'])
        if not table.headers:
            return FixtureResult(passed=True, message="DatabaseEnvironment (empty)")
        cmd = table.headers[0].strip().lower()
        if cmd == "rollback":
            ctx.conn.rollback() if hasattr(ctx.conn, "rollback") else ctx.conn.rollback()
            return FixtureResult(passed=True, message="DatabaseEnvironment rollback")
        if cmd == "commit":
            ctx.conn.commit() if hasattr(ctx.conn, "commit") else ctx.conn.commit()
            return FixtureResult(passed=True, message="DatabaseEnvironment commit")
        return FixtureResult(
            passed=False, message=f"DatabaseEnvironment unknown command: {cmd!r}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _build_proc_call_candidates(
    name: str, param_names: list[str], dialect: str
) -> list[str]:
    """Return an ordered list of call statements per dialect.

    Multiple candidates only where a fallback is sensible (Postgres: SELECT/CALL).
    """
    if dialect == "mssql":
        if param_names:
            args = ", ".join(f"@{p} = :{p}" for p in param_names)
            return [f"EXEC {name} {args}"]
        return [f"EXEC {name}"]
    if dialect == "oracle":
        if param_names:
            args = ", ".join(f"{p} => :{p}" for p in param_names)
            return [f"BEGIN {name}({args}); END;"]
        return [f"BEGIN {name}; END;"]
    # Postgres / generic: SELECT first, CALL as fallback.
    if param_names:
        args = ", ".join(f"{p} := :{p}" for p in param_names)
        return [f"SELECT {name}({args})", f"CALL {name}({args})"]
    return [f"SELECT {name}()", f"CALL {name}()"]


def _cell_to_bind_value(cell: str, ctx: FixtureContext) -> Any:
    stripped = cell.strip()
    if stripped == "" or stripped.lower() == "null":
        return None
    if stripped.startswith("<<"):
        return ctx.symbols.get(stripped[2:])
    return stripped


def _call_proc(
    name: str,
    param_names: list[str],
    row: list[str],
    ctx: FixtureContext,
    expect_exception: bool,
    expected_code: str = "",
) -> FixtureResult:
    binds: dict[str, Any] = {}
    for i, p in enumerate(param_names):
        binds[p] = _cell_to_bind_value(row[i], ctx) if i < len(row) else None

    # Dialect-specific procedure call:
    # * Postgres:   SELECT name(p := :p) → fallback CALL name(p := :p) for procedures
    # * Oracle:     BEGIN name(p => :p); END;
    # * SQL Server: EXEC name @p = :p
    dialect_name = ctx.conn.engine.dialect.name
    candidates = _build_proc_call_candidates(name, param_names, dialect_name)

    last_err: Any = None
    for stmt in candidates:
        # Each attempt in its own savepoint — otherwise an error on Postgres would leave
        # the outer TX in "aborted" state and any subsequent statement (including the
        # runner's RELEASE SAVEPOINT) would fail.
        sp = ctx.conn.begin_nested()
        try:
            ctx.conn.execute(text(stmt), binds)
        except DBAPIError as e:
            if sp.is_active:
                sp.rollback()
            last_err = wrap_dbapi_error(e, sql=stmt, binds=binds)
            msg_lower = last_err.message.lower()
            # With multiple candidates, advance to the next variant when the error
            # signals that this routing construct wasn't the right one.
            if (
                "is a procedure" in msg_lower
                or "use call" in msg_lower
                or "perform select" in msg_lower
            ):
                continue
            break
        else:
            sp.commit()
            if expect_exception:
                return FixtureResult(
                    passed=False,
                    message="expected exception was NOT raised",
                    details=f"SQL:\n{stmt}\nBinds: {binds}",
                )
            return FixtureResult(passed=True, message=f"OK ({stmt.split('(')[0]})")

    if expect_exception:
        if not expected_code:
            return FixtureResult(passed=True, message=f"exception as expected: {last_err}")
        # Code comparison: numeric (ORA code) or SQLSTATE (5-char alphanumeric)
        ec = expected_code.strip()
        if ec.isdigit():
            if str(last_err.code) == ec or last_err.sqlstate == ec:
                return FixtureResult(
                    passed=True, message=f"exception {ec} as expected: {last_err.message}"
                )
        else:
            if last_err.sqlstate == ec:
                return FixtureResult(
                    passed=True, message=f"exception SQLSTATE={ec} as expected"
                )
        return FixtureResult(
            passed=False,
            message=(
                f"exception raised but wrong code (expected {ec}, "
                f"got code={last_err.code} sqlstate={last_err.sqlstate!r})"
            ),
            details=str(last_err),
        )
    return FixtureResult(
        passed=False,
        message=f"Execute Procedure fail: {last_err}",
        details=str(last_err),
    )


def _cells_equal(expected: str, actual: Any) -> bool:
    """Compare an expected cell (always a string) to a DB value.

    Conventions:
    * empty cell and ``null``                → expect NULL/None
    * ``true``/``false`` (case-insensitive)  → expect a bool value
    * otherwise: string representation of the DB value, case-insensitive, trimmed,
      equals the expected string.
    """
    exp_norm = (expected or "").strip()
    if exp_norm == "" or exp_norm.lower() == "null":
        return actual is None
    if actual is None:
        return False
    exp_lower = exp_norm.lower()
    if isinstance(actual, bool):
        if exp_lower in ("true", "t", "1"):
            return actual is True
        if exp_lower in ("false", "f", "0"):
            return actual is False
        return False
    return str(actual).strip().lower() == exp_lower


def _row_mismatch(
    sql: str,
    expected_headers: list[str],
    expected_rows: list[list[str]],
    actual_cols: list[str],
    actual_rows: list[tuple[Any, ...]],
) -> FixtureResult:
    buf = StringIO()
    buf.write("SQL:\n")
    buf.write(sql.strip() + "\n\n")
    buf.write("Expected (")
    buf.write(", ".join(expected_headers))
    buf.write("):\n")
    for r in expected_rows:
        buf.write("  | " + " | ".join(r) + " |\n")
    buf.write("\nActual (")
    buf.write(", ".join(actual_cols))
    buf.write("):\n")
    for r in actual_rows:
        buf.write("  | " + " | ".join(_fmt_cell(c) for c in r) + " |\n")
    return FixtureResult(
        passed=False, message="Row-Mismatch", details=buf.getvalue()
    )


def _fmt_cell(v: Any) -> str:
    if v is None:
        return "null"
    return str(v)


def _format_sql_block(sql: str, err: Any) -> str:
    return f"SQL:\n{sql.strip()}\n\nError: {err}"
