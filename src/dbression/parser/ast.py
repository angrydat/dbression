"""AST nodes for parsed FitNesse-wiki files."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Directive:
    """A wiki directive such as `!path lib/*.jar` or `!define foo=bar`."""

    name: str
    value: str
    line: int


@dataclass(slots=True)
class Table:
    """A fixture table. `name` is the fixture identifier (first cell of the first row).

    `header_args` are the remaining cells of the header row (e.g. the SQL statement in
    ``Query|<sql>``). `headers` is the second row (column headers for the data), if any.
    `rows` are the data rows. For fixtures like ``Execute|<sql>`` without data rows,
    `headers` is empty.
    """

    name: str
    header_args: list[str] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    rows: list[list[str]] = field(default_factory=list)
    line: int = 0


@dataclass(slots=True)
class Page:
    """A single `.wiki` file (one test page).

    `tags` come from an optional YAML front-matter block (``---\\nSuites: critical\\n---``)
    at the top of the file (msgis convention for FitNesse tags); multiple values may be
    separated by commas or whitespace.
    """

    path: Path
    name: str
    directives: list[Directive] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Suite:
    """A suite — a directory containing `_root.wiki`, test pages, and optionally
    `SuiteSetUp` / `SuiteTearDown`.

    Sub-suites are subdirectories with their own `_root.wiki`. Suite directives
    (`DatabaseEnvironment`, `ConnectUsingFile`, …) are read by the runner from the suite
    itself first, falling back to the parent suite's AST.
    """

    root: Path
    name: str
    root_page: Page | None = None
    setup: Page | None = None
    teardown: Page | None = None
    pages: list[Page] = field(default_factory=list)
    subsuites: list["Suite"] = field(default_factory=list)
