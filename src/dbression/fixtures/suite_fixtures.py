"""Pseudo-fixtures for suite-level directives that DBFit writes as tables
(``DatabaseEnvironment``, ``ConnectUsingFile``, ``import fixture``).

These are processed by the runner directly for engine / suite configuration and are not
counted as test steps. We only register them so the fixture-resolution phase doesn't
flag them as "unknown fixture".
"""
from __future__ import annotations

from dbression.fixtures.base import Fixture, FixtureContext, FixtureResult, register
from dbression.parser.ast import Table


@register("DatabaseEnvironment")
class _DatabaseEnvironment(Fixture):
    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:
        # Processed by the runner before connect — no-op here.
        return FixtureResult(
            passed=True,
            message=f"DatabaseEnvironment={table.header_args[0] if table.header_args else '?'}",
        )


@register("import fixture")
class _ImportFixture(Fixture):
    def run(self, table: Table, ctx: FixtureContext) -> FixtureResult:
        # No Java fixture class loading in dbression; ignored.
        return FixtureResult(passed=True, message="import fixture (ignored)")
