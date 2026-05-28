from __future__ import annotations

import os
from pathlib import Path

import pytest

from dbression.db import load_connection_properties


def test_env_var_substitution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DBRESSION_TEST_HOST", "db.example.com")
    monkeypatch.setenv("DBRESSION_TEST_USER", "tester")
    src = tmp_path / "x.connection.properties"
    src.write_text(
        "service=${DBRESSION_TEST_HOST}\n"
        "username=${DBRESSION_TEST_USER}\n"
        "password=secret\n"
        "database=mydb\n",
        encoding="utf-8",
    )
    cfg = load_connection_properties(src)
    assert cfg.service == "db.example.com"
    assert cfg.username == "tester"
    assert cfg.password == "secret"
    assert cfg.extra is not None
    assert cfg.extra["database"] == "mydb"


def test_undefined_env_var_raises(tmp_path: Path) -> None:
    src = tmp_path / "x.connection.properties"
    src.write_text("service=${DBRESSION_UNDEFINED_VAR_XYZ}\n", encoding="utf-8")
    if "DBRESSION_UNDEFINED_VAR_XYZ" in os.environ:
        del os.environ["DBRESSION_UNDEFINED_VAR_XYZ"]
    with pytest.raises(KeyError):
        load_connection_properties(src)
