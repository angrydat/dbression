"""Tests for the plugin loader (entry-points + the DBRESSION_PLUGINS env var)."""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from dbression.fixtures import REGISTRY, resolve_fixture
from dbression.fixtures.plugins import _LOADED, load_plugins


def _write_plugin_module(
    tmp_path: Path, modname: str, fixture_name: str = "Custom Demo"
) -> None:
    src = tmp_path / f"{modname}.py"
    src.write_text(
        textwrap.dedent(
            f"""
            from dbression.fixtures.base import Fixture, FixtureContext, FixtureResult, register

            @register({fixture_name!r})
            class _DemoFixture(Fixture):
                def run(self, table, ctx: FixtureContext) -> FixtureResult:
                    return FixtureResult(passed=True, message="demo")
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )


def _reset_plugin_state(modname: str) -> None:
    """Ensure the plugin can be freshly loaded again."""
    _LOADED.discard(modname)
    sys.modules.pop(modname, None)


def test_load_via_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_plugin_module(tmp_path, "demo_plugin_env", fixture_name="Custom Env Fixture")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("DBRESSION_PLUGINS", "demo_plugin_env")
    _reset_plugin_state("demo_plugin_env")

    fresh = load_plugins()
    assert "demo_plugin_env" in fresh
    assert resolve_fixture("Custom Env Fixture") is not None


def test_load_via_entry_point(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_plugin_module(tmp_path, "demo_plugin_ep", fixture_name="Custom EP Fixture")
    monkeypatch.syspath_prepend(str(tmp_path))
    _reset_plugin_state("demo_plugin_ep")

    class _FakeEP:
        value = "demo_plugin_ep"

    with patch(
        "dbression.fixtures.plugins.entry_points",
        return_value=[_FakeEP()],
    ):
        fresh = load_plugins()

    assert "demo_plugin_ep" in fresh
    assert resolve_fixture("Custom EP Fixture") is not None


def test_failed_plugin_warns_but_does_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DBRESSION_PLUGINS", "this.module.does.not.exist.xyz")
    _LOADED.discard("this.module.does.not.exist.xyz")

    with pytest.warns(UserWarning, match="could not be loaded"):
        fresh = load_plugins()

    # Plugin was not loaded → not in `fresh`
    assert "this.module.does.not.exist.xyz" not in fresh
    # But marked as "seen" so we don't keep warning about it
    assert "this.module.does.not.exist.xyz" in _LOADED


def test_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_plugin_module(tmp_path, "demo_plugin_idem", fixture_name="Custom Idem Fixture")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setenv("DBRESSION_PLUGINS", "demo_plugin_idem")
    _reset_plugin_state("demo_plugin_idem")

    first = load_plugins()
    second = load_plugins()
    assert "demo_plugin_idem" in first
    # The second invocation must not freshly load anything again
    assert "demo_plugin_idem" not in second
