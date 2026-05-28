"""Suite runner with rollback-per-test as the default."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from sqlalchemy.engine import Engine

from dbression.db import load_connection_properties, make_engine, resolve_connection_file
from dbression.fixtures import FixtureContext, FixtureResult, resolve_fixture
from dbression.fixtures.base import StoredQuery
from dbression.parser.ast import Page, Suite, Table
from dbression.symbols import SymbolTable


CommitMode = Literal["test", "page"]


@dataclass(slots=True)
class TableResult:
    name: str
    result: FixtureResult
    duration: float


@dataclass(slots=True)
class PageResult:
    name: str
    path: Path
    tables: list[TableResult] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(t.result.passed for t in self.tables)


@dataclass(slots=True)
class SuiteResult:
    name: str
    pages: list[PageResult] = field(default_factory=list)
    setup_result: PageResult | None = None
    teardown_result: PageResult | None = None
    error: str | None = None
    subsuites: list["SuiteResult"] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        own = sum(1 for p in self.pages if p.passed)
        return own + sum(s.passed_count for s in self.subsuites)

    @property
    def failed_count(self) -> int:
        own = sum(1 for p in self.pages if not p.passed)
        return own + sum(s.failed_count for s in self.subsuites)

    @property
    def total_count(self) -> int:
        return len(self.pages) + sum(s.total_count for s in self.subsuites)


# Fixtures handled by the runner directly (not reported as a test-step result).
_SUITE_DIRECTIVE_FIXTURES = {"databaseenvironment", "connectusingfile", "import fixture"}


def _is_suite_directive(table: Table) -> bool:
    norm = " ".join(table.name.strip().lower().split())
    return norm in _SUITE_DIRECTIVE_FIXTURES


def _scan_engine_config(page: Page | None) -> tuple[str | None, str | None]:
    """Scan a page for `DatabaseEnvironment` and `ConnectUsingFile` directives."""
    if page is None:
        return None, None
    env: str | None = None
    props: str | None = None
    for tbl in page.tables:
        norm = tbl.name.strip().lower()
        if norm == "databaseenvironment":
            if tbl.header_args:
                env = tbl.header_args[0]
            if len(tbl.headers) >= 2 and tbl.headers[0].lower() == "connectusingfile":
                props = tbl.headers[1]
        elif norm == "connectusingfile":
            if tbl.header_args:
                props = tbl.header_args[0]
    return env, props


def _resolve_engine_config(suite: Suite) -> tuple[str, str]:
    """Look up DatabaseEnvironment + ConnectUsingFile.

    Precedence: SuiteSetUp (override) → _root → raise.
    """
    env, props = _scan_engine_config(suite.setup)
    if not env or not props:
        re, rp = _scan_engine_config(suite.root_page)
        env = env or re
        props = props or rp
    if not env:
        raise ValueError(f"Suite {suite.name} does not set a DatabaseEnvironment")
    if not props:
        raise ValueError(f"Suite {suite.name} has no ConnectUsingFile directive")
    return env, props


def build_engine_for_suite(suite: Suite) -> Engine:
    """Look up DatabaseEnvironment + ConnectUsingFile first in the suite itself, then in
    parent directories (each carrying its own `_root.wiki`).
    """
    try:
        env, declared_props = _resolve_engine_config(suite)
    except ValueError:
        # Walk up: try parent directories' _root.wiki
        env_str: str | None = None
        props_str: str | None = None
        for parent in suite.root.parents:
            root_wiki = parent / "_root.wiki"
            if not root_wiki.is_file():
                continue
            from dbression.parser.wiki import parse_wiki

            parent_root_page = parse_wiki(root_wiki)
            re, rp = _scan_engine_config(parent_root_page)
            env_str = env_str or re
            props_str = props_str or rp
            if env_str and props_str:
                break
        if not env_str or not props_str:
            raise  # original ValueError
        env, declared_props = env_str, props_str
    props_path = resolve_connection_file(declared_props, suite.root)
    cfg = load_connection_properties(props_path)
    return make_engine(env, cfg)


@dataclass(slots=True)
class TagFilter:
    """Tag-based page filtering — the runner ↔ CLI interface.

    `only` (allow-list): if non-empty, a page only runs when it carries at least one of
    these tags. `skip` (deny-list): pages carrying any of these tags are skipped
    (even if they would match `only`). Tag matching is case-insensitive.
    """

    only: tuple[str, ...] = ()
    skip: tuple[str, ...] = ()

    def page_allowed(self, page: Page) -> bool:
        page_tags_lower = {t.lower() for t in page.tags}
        if self.only and not page_tags_lower.intersection(t.lower() for t in self.only):
            return False
        if self.skip and page_tags_lower.intersection(t.lower() for t in self.skip):
            return False
        return True


def run_suite(
    suite: Suite,
    engine: Engine,
    commit_mode: CommitMode = "test",
    symbols: SymbolTable | None = None,
    tag_filter: TagFilter | None = None,
    stored: dict[str, StoredQuery] | None = None,
) -> SuiteResult:
    """Run a suite recursively (including sub-suites).

    **Transaction model (DBFit-compatible):** one connection + one transaction per suite.
    SuiteSetUp + all test pages + SuiteTearDown all run inside it. Test isolation is
    achieved via savepoints (commit_mode='test' → rollback to savepoint, commit_mode='page'
    → release savepoint). The suite transaction is always rolled back at the end (DBFit
    issues Rollback explicitly in TearDown; we do it defensively as well).
    """
    if symbols is None:
        symbols = SymbolTable()
    if stored is None:
        stored = {}
    result = SuiteResult(name=suite.name)

    try:
        with engine.connect() as conn:
            tx = conn.begin()
            try:
                # SuiteSetUp — runs inside the suite TX, no commit/rollback of its own.
                if suite.setup is not None:
                    result.setup_result = _run_page_in_tx(
                        suite.setup, conn, symbols, stored, isolate=False
                    )
                    if not result.setup_result.passed:
                        result.error = f"SuiteSetUp failed: {result.setup_result.name}"
                        return result

                # Test pages — each in its own savepoint, optionally tag-filtered.
                for page in suite.pages:
                    if tag_filter is not None and not tag_filter.page_allowed(page):
                        continue
                    isolate = commit_mode == "test"
                    pr = _run_page_in_tx(page, conn, symbols, stored, isolate=isolate)
                    result.pages.append(pr)

                # Sub-suites: recursive, with their own engine if directives differ.
                for sub in suite.subsuites:
                    sub_res = _run_subsuite(
                        sub, engine, conn, commit_mode, symbols, tag_filter, stored
                    )
                    result.subsuites.append(sub_res)

                # SuiteTearDown — runs inside the suite TX. Fixtures like
                # `DatabaseEnvironment|Rollback` may roll back the TX explicitly; the
                # connection stays valid.
                if suite.teardown is not None:
                    result.teardown_result = _run_page_in_tx(
                        suite.teardown, conn, symbols, stored, isolate=False
                    )
            finally:
                # Defensive rollback of the entire suite TX. If TearDown already rolled
                # back, tx.is_active is False and we do nothing.
                if tx.is_active:
                    tx.rollback()
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"

    return result


def _run_subsuite(
    sub: Suite,
    parent_engine: Engine,
    parent_conn,
    commit_mode: CommitMode,
    symbols: SymbolTable,
    tag_filter: TagFilter | None = None,
    stored: dict[str, StoredQuery] | None = None,
) -> SuiteResult:
    """Run a sub-suite. If it has its own engine directives, use a local engine; otherwise
    run on the parent engine (with its own connection, for clean TX isolation).
    """
    sub_env, sub_props = _scan_engine_config(sub.setup)
    if not sub_env or not sub_props:
        re, rp = _scan_engine_config(sub.root_page)
        sub_env = sub_env or re
        sub_props = sub_props or rp

    if sub_env and sub_props:
        try:
            sub_props_path = resolve_connection_file(sub_props, sub.root)
            sub_cfg = load_connection_properties(sub_props_path)
            sub_engine = make_engine(sub_env, sub_cfg)
        except Exception as e:
            return SuiteResult(name=sub.name, error=f"Engine build: {type(e).__name__}: {e}")
        try:
            return run_suite(sub, sub_engine, commit_mode, symbols, tag_filter, stored)
        finally:
            sub_engine.dispose()

    return run_suite(sub, parent_engine, commit_mode, symbols, tag_filter, stored)


def _run_page_in_tx(
    page: Page,
    conn,
    symbols: SymbolTable,
    stored: dict[str, StoredQuery],
    isolate: bool,
) -> PageResult:
    """Run all fixture tables of a page inside the existing suite TX.

    If `isolate=True`, each page wraps its tables in a savepoint that is released on
    success and rolled back on failure. If False, everything runs directly inside the
    suite TX (used for SuiteSetUp / SuiteTearDown).
    """
    pr = PageResult(name=page.name, path=page.path)
    savepoint = conn.begin_nested() if isolate else None
    try:
        ctx = FixtureContext(conn=conn, symbols=symbols, stored=stored)
        for table in page.tables:
            if _is_suite_directive(table):
                continue
            start = time.perf_counter()
            fixture_cls = resolve_fixture(table.name)
            if fixture_cls is None:
                res = FixtureResult(
                    passed=False,
                    message=f"Unknown fixture: {table.name!r}",
                )
            else:
                try:
                    res = fixture_cls().run(table, ctx)
                except Exception as e:  # pragma: no cover - defensive
                    res = FixtureResult(
                        passed=False,
                        message=f"Fixture crash: {type(e).__name__}",
                        details=str(e),
                    )
            pr.tables.append(
                TableResult(name=table.name, result=res, duration=time.perf_counter() - start)
            )
            if not res.passed:
                if savepoint is not None and savepoint.is_active:
                    savepoint.rollback()
                return pr
        if savepoint is not None and savepoint.is_active:
            savepoint.commit()
    except Exception as e:
        pr.error = f"{type(e).__name__}: {e}"
        if savepoint is not None and savepoint.is_active:
            savepoint.rollback()
    return pr
