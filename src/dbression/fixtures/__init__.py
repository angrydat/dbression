"""Fixture registry and base class."""
from dbression.fixtures.base import (
    Fixture,
    FixtureContext,
    FixtureResult,
    REGISTRY,
    register,
    resolve_fixture,
)

# Importing the modules registers their fixtures via the decorator.
from dbression.fixtures import suite_fixtures  # noqa: F401
from dbression.fixtures import basic  # noqa: F401
from dbression.fixtures import inspect_and_store  # noqa: F401

# Load third-party fixtures via entry-points / the DBRESSION_PLUGINS env var.
# Important: AFTER the built-in imports, so that `register` & friends are already
# available in the package namespace if a plugin uses
# `from dbression.fixtures import register` instead of importing directly from
# `dbression.fixtures.base`.
from dbression.fixtures.plugins import load_plugins as _load_plugins  # noqa: E402

_load_plugins()

__all__ = [
    "Fixture",
    "FixtureContext",
    "FixtureResult",
    "REGISTRY",
    "register",
    "resolve_fixture",
]
