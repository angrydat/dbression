"""Fixture base class, context, and registry.

DBFit names fixtures like ``Execute Procedure``, ``Execute Procedure Expect Exception``,
etc. We map the fixture name (case-insensitive, normalized to lower + single spaces) to a
Python class that implements ``run()``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, ClassVar

from sqlalchemy.engine import Connection

from dbression.parser.ast import Table
from dbression.symbols import SymbolTable


@dataclass(slots=True)
class FixtureResult:
    """Result of a single fixture invocation.

    `passed` is True when the fixture met its expectation.
    `message` is a short status line (single line).
    `details` carries the verbose output on failure (exception, row diff, etc.).
    """

    passed: bool
    message: str = ""
    details: str = ""


@dataclass(slots=True)
class StoredQuery:
    """Stored query result for `Store Query` / `Compare Stored Queries`."""

    columns: list[str]
    rows: list[tuple]


@dataclass(slots=True)
class FixtureContext:
    """Runtime context the runner passes to each fixture."""

    conn: Connection
    symbols: SymbolTable
    # Stash for `Store Query` — spans the whole suite so `Compare Stored Queries` can
    # reference snapshots across multiple pages.
    stored: dict[str, StoredQuery] = field(default_factory=dict)
    # Reserved for future fixture side effects.
    notes: list[str] = field(default_factory=list)


class Fixture:
    """Abstract fixture base class.

    Concrete fixtures implement ``run(table, context)``. The constructor takes no
    arguments — instances are stateless throwaway objects, one per table evaluation.
    """

    name: ClassVar[str] = ""

    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:  # pragma: no cover
        raise NotImplementedError


REGISTRY: dict[str, type[Fixture]] = {}


def _normalize(name: str) -> str:
    return " ".join(name.strip().lower().split())


def register(name: str) -> Callable[[type[Fixture]], type[Fixture]]:
    """Decorator: register a fixture class under a display name.

    Multiple registrations (aliases) are allowed — just apply the decorator multiple times.
    """

    def deco(cls: type[Fixture]) -> type[Fixture]:
        REGISTRY[_normalize(name)] = cls
        if not cls.name:
            cls.name = name
        return cls

    return deco


def resolve_fixture(name: str) -> type[Fixture] | None:
    return REGISTRY.get(_normalize(name))
