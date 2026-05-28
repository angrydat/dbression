"""Plugin loader for custom fixtures.

Third-party packages extend dbression via Python entry-points:

```toml
# pyproject.toml of a plugin package
[project.entry-points."dbression.fixtures"]
my-fixtures = "my_plugin.fixtures"
```

The value is a module path. On load the module is imported — the ``@register`` decorators
fire automatically and add the fixtures to the global registry.

For ad-hoc extensions without packaging there is also the environment variable
``DBRESSION_PLUGINS`` (comma-separated module names):

```bash
DBRESSION_PLUGINS=my_team.fixtures,helpers.dbression_ext  dbression run tests/
```

Both mechanisms are idempotent — calling ``load_plugins()`` more than once is harmless.
Import errors of individual plugins emit a warning instead of stopping the run.
"""
from __future__ import annotations

import importlib
import os
import sys
import warnings
from importlib.metadata import entry_points

_LOADED: set[str] = set()


_ENTRY_POINT_GROUP = "dbression.fixtures"
_ENV_VAR = "DBRESSION_PLUGINS"


def load_plugins() -> list[str]:
    """Load every available plugin from entry-points and the ``DBRESSION_PLUGINS`` env var.

    Returns the list of plugin identifiers that were freshly imported (for diagnostics).
    Idempotent — already-loaded plugins are skipped.
    """
    fresh: list[str] = []
    for ident in _entry_point_targets():
        if _import_target(ident):
            fresh.append(ident)
    for ident in _env_var_targets():
        if _import_target(ident):
            fresh.append(ident)
    return fresh


def _entry_point_targets() -> list[str]:
    try:
        eps = entry_points(group=_ENTRY_POINT_GROUP)
    except TypeError:  # pragma: no cover - very old importlib.metadata
        eps = entry_points().get(_ENTRY_POINT_GROUP, [])  # type: ignore[attr-defined]
    targets: list[str] = []
    for ep in eps:
        # ep.value for `pkg.mod` or `pkg.mod:attr` — we want just the module part.
        value = getattr(ep, "value", None) or str(ep)
        module = value.split(":", 1)[0].strip()
        if module:
            targets.append(module)
    return targets


def _env_var_targets() -> list[str]:
    raw = os.environ.get(_ENV_VAR, "")
    return [t.strip() for t in raw.split(",") if t.strip()]


def _import_target(module_name: str) -> bool:
    if module_name in _LOADED:
        return False
    try:
        importlib.import_module(module_name)
    except Exception as exc:  # noqa: BLE001 — plugin errors must not stop the run
        warnings.warn(
            f"dbression plugin {module_name!r} could not be loaded: "
            f"{type(exc).__name__}: {exc}",
            stacklevel=2,
        )
        # Remember it even after failure so we don't loop warning about it.
        _LOADED.add(module_name)
        return False
    _LOADED.add(module_name)
    if os.environ.get("DBRESSION_DEBUG"):
        print(f"dbression: plugin loaded: {module_name}", file=sys.stderr)
    return True
