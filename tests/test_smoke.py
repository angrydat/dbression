from __future__ import annotations

import subprocess
import sys

from typer.testing import CliRunner

import dbression
from dbression.cli import app


def test_version_constant() -> None:
    assert dbression.__version__ == "0.1.0"


def test_cli_version_command() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "dbression 0.1.0" in result.stdout


def test_cli_entry_point_subprocess() -> None:
    """Make sure `python -m dbression.cli` runs (independent of the installed script)."""
    result = subprocess.run(
        [sys.executable, "-m", "dbression.cli", "version"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "dbression 0.1.0" in result.stdout
