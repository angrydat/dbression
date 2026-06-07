# Changelog

All notable changes to `dbression` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] — 2026-06-08

### Added

- **Single-file runs.** `dbression run path/to/MyTest.test.md` (or `.wiki`) now runs a
  single test, mirroring DBFit: a file is one *Test* (many fixtures), a directory is a
  *Suite*. The containing directory's `SuiteSetUp` / `SuiteTearDown` and `_root`
  (connection + `DatabaseEnvironment`) are included automatically. A self-contained
  `.test.md` carrying its own `<!-- dbression:env=… -->` / `<!-- dbression:connection=… -->`
  directives runs standalone.
- **Live progress.** Runs now show a spinner, an `x/y fixtures` counter, elapsed time, and
  a status line naming the fixture/query currently executing. On by default at a TTY;
  silenced automatically when output is piped or in CI. Toggle with `--progress` /
  `--no-progress`.
- **`--details` / `-d`.** Prints each fixture's result green/red as it runs (DBFit-web-UI
  style), so a `.test.md` viewed in `glow` has a matching colored CLI run alongside it.

## [0.2.0] — 2026-06-01

### Added

- **SQLite as a `DatabaseEnvironment`.** Use `DatabaseEnvironment | sqlite` (alias
  `sqlite3`) with `service=:memory:` or `service=<path-to-db-file>` in
  `connection.properties`. No native deps — uses the Python stdlib `sqlite3`
  driver via SQLAlchemy. `Execute Procedure` does not apply (SQLite has no
  stored procedures); everything else (`Query`, `Execute`, `Insert`, `Delete`,
  `Inspect *`, `Update`, captures, substitutions) works the same as on the
  other backends.

## [0.1.2] — 2026-06-01

SQL Server live-verification release. A real-world MSSQL DBFit suite (regression tests,
stored-procedure-driven, square-bracket identifiers throughout)
runs end-to-end against an MSSQL Server 2019 via `pymssql` with no changes to the
underlying `.wiki` files.

### Fixed

- **Console reporter swallowed `[…]` in failure details.** Rich's inline-markup
  parser interpreted MSSQL square-bracket identifiers like `[dbo].ORDER` as
  style tags and stripped them from the displayed SQL — making failure output
  misleading. Reporter now prints fixture details with `markup=False`, so the
  SQL you see is the SQL that ran.

### Changed

- **`__version__` now derives from package metadata** (`importlib.metadata`).
  One source of truth — `pyproject.toml`. Eliminates the version-drift class of
  bug where the CLI banner kept saying `0.1.0` after releases.

## [0.1.1] — 2026-06-01

First Oracle-verified release. KBGSuite, a real-world DBFit suite of network-topology
tests against an Oracle 19c instance, runs end-to-end (6/6 pages green) via dbression
with no changes to the underlying `.wiki` files.

### Added

- **`Ordered Query`** fixture for tests where row order is part of the contract.
  Default `Query` is now unordered (set-based) — see *Changed* below.
- **Function return values in `Execute Procedure`**: a `?` column header (DBFit
  convention) is now captured from the call result and compared against the
  corresponding cell. Works for Oracle SQL functions called via `SELECT … FROM dual`.

### Changed

- **`Query` is now set-based (multiset) by default**, matching DBFit's `RowFixture`
  semantics: expected rows must match actual rows regardless of order, with no
  surplus and nothing missing. Tests previously written for the strict positional
  comparison should still pass (a multiset matches if the list matches); tests that
  used a hand-curated row order without an `ORDER BY` will now pass where they
  previously failed.
- **Numeric cell comparison** uses `Decimal` instead of string equality. Oracle
  `NUMBER` columns arrive as `Decimal('2502.0')` and now match the wiki cell `"2502"`.
- **Oracle stored-routine calls** transparently try `BEGIN … END;`, `SELECT … FROM dual`
  and positional variants in order. Errors with PLS-00103 / PLS-00306 (which usually
  indicate "this is a FUNCTION, not a PROCEDURE") trigger the next candidate.
- **Column-name lookup in result sets** falls back to positional mapping when the
  expected header count equals the actual column count. Covers idioms like
  `select count(*)` where the implicit column name is `COUNT(*)`.

### Fixed

- **`Update` fixture semantics**: the `=` suffix on a column header marks a **SET**
  column (previously WHERE), bare headers mark **WHERE** columns (previously SET).
  This is the DBFit convention; v0.1.0 had it inverted. If you wrote any `Update`
  fixtures against v0.1.0, swap the `=` markers across.

## [0.1.0] — 2026-05-29

Initial public release. Functional core that runs real-world DBFit suites against PostgreSQL,
with code paths in place for SQL Server and Oracle.

### Added

- **Wiki parser** for the DBFit subset that real-world suites actually use, including
  `!- ... -!` multi-line escapes, Oracle `q'~ ... ~'` custom quoting, YAML-style
  front-matter for tags, and lenient detection of fixture-prefixed tables without `!|`.
- **Executable Markdown** (`.test.md`) — a Markdown-based test format that renders cleanly
  in any viewer and runs the same way `.wiki` files do. Conventions: `### <Fixture> [args]`
  headings, fenced ```` ```sql ```` blocks for SQL, Markdown tables for data rows, and
  `<!-- dbression:env=… -->` style HTML-comment directives.
- **`dbression convert`** — one-shot or recursive migration tool that turns `.wiki` suites
  into `.test.md`. Both formats coexist; Markdown wins at runtime.
- **Fixtures**:
  - `Query` with `>>capture` / `<<read` / `:bind` / `_:text-substitution`
  - `Execute` / `Execute Ddl`
  - `Execute Procedure` (dialect-aware: `SELECT`/`CALL` for PG, `EXEC` for MSSQL,
    `BEGIN…END;` for Oracle)
  - `Execute Procedure Expect Exception` with SQLSTATE / ORA-code matching
  - `Insert` (with `>>capture` via `RETURNING`) and `Delete`
  - `Set Parameter` with Java-type-hint conversion
  - `Inspect Table` / `Inspect View` / `Inspect Procedure` with optional body comparison
  - `Store Query` and `Compare Stored Queries`
- **Multi-database support** via SQLAlchemy 2.0:
  - PostgreSQL through `psycopg` v3 — live-verified
  - SQL Server through `pymssql` (pure Python, no ODBC stack needed) — code-complete
  - Oracle through `oracledb` (thin mode by default, optional thick mode via
    `DBRESSION_ORACLE_CLIENT_LIB_DIR`) — code-complete
- **Runner** with a DBFit-compatible transaction model: one connection + one transaction
  per suite, with savepoints per test for the default rollback-per-test isolation. A
  `--commit-mode page` flag re-enables the DBFit commit-per-page behavior.
- **CLI**: `dbression run <path>`, `dbression convert`, `dbression version`. Tag-based
  filtering via `--tag` / `--skip-tag`. Verbose output via `-v`.
- **Reporters**:
  - Rich console output (pytest-style ✓/✗ tree, full exception bodies, agentic-friendly
    plain-text failures)
  - JUnit XML via `--junit-xml` for Bitbucket Pipelines, Jenkins, GitLab CI, etc.
  - JSON via `--json` for tooling / LLM consumption
- **Plugin entry-points** under the `dbression.fixtures` group, plus the
  `DBRESSION_PLUGINS` environment variable for ad-hoc / unpackaged extensions.
- **Connection configuration** via DBFit-compatible `connection.properties`, including
  `${ENV_VAR}` expansion and walk-up resolution of declared paths.

### Known limitations

- `Update` fixture is stubbed — implementation deferred until a real-world example calls
  for it.
- Live Oracle connectivity may require InstantClient (thick mode) against servers that
  reject `python-oracledb` thin-mode authentication. Configuration is via
  `DBRESSION_ORACLE_CLIENT_LIB_DIR`.

[Unreleased]: https://github.com/angrydat/dbression/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/angrydat/dbression/releases/tag/v0.3.0
[0.2.0]: https://github.com/angrydat/dbression/releases/tag/v0.2.0
[0.1.2]: https://github.com/angrydat/dbression/releases/tag/v0.1.2
[0.1.1]: https://github.com/angrydat/dbression/releases/tag/v0.1.1
[0.1.0]: https://github.com/angrydat/dbression/releases/tag/v0.1.0
