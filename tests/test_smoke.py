from __future__ import annotations

import re
import subprocess
import sys

from typer.testing import CliRunner

import dbression
from dbression.cli import app

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+([+-].*)?$")


def test_version_constant() -> None:
    assert _SEMVER_RE.match(dbression.__version__), dbression.__version__


def test_cli_version_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert f"dbression {dbression.__version__}" in result.stdout


def test_cli_entry_point_subprocess() -> None:
    """Make sure `python -m dbression.cli` runs (independent of the installed script)."""
    result = subprocess.run(
        [sys.executable, "-m", "dbression.cli", "version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert f"dbression {dbression.__version__}" in result.stdout
