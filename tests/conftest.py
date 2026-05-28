"""Test setup: enables Oracle thick mode automatically if a local InstantClient is
unpacked under ``.instantclient/`` inside the repo.

Dev convention:
* Optionally unpack InstantClient into ``<repo>/.instantclient/instantclient_*/``
  (see the README for the download URL).
* Or just export ``DBRESSION_ORACLE_CLIENT_LIB_DIR`` yourself.

If neither is set the Oracle adapter runs in thin mode — live tests against servers that
reject thin-mode auth will then fail (which is fine; those tests are gated behind
``skipif`` for reachability anyway).
"""
from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_IC_BASE = _REPO_ROOT / ".instantclient"


def _autodetect_instantclient() -> str | None:
    if not _IC_BASE.is_dir():
        return None
    for child in sorted(_IC_BASE.iterdir()):
        if child.is_dir() and (child / "libclntsh.so").exists():
            return str(child)
    return None


if "DBRESSION_ORACLE_CLIENT_LIB_DIR" not in os.environ:
    detected = _autodetect_instantclient()
    if detected:
        os.environ["DBRESSION_ORACLE_CLIENT_LIB_DIR"] = detected
