# Changelog

All notable changes to `dbression` are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/angrydat/dbression/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/angrydat/dbression/releases/tag/v0.1.0
