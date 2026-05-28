"""Database error representation and platform-code extraction from SQLAlchemy exceptions."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import DBAPIError


@dataclass(slots=True)
class DBError(Exception):
    """Driver-agnostic database error representation.

    ``code`` is a numeric platform code (Oracle: ORA-NNNNN without the prefix, as int;
    Postgres: 0 because Postgres uses SQLSTATE instead of codes).
    ``sqlstate`` is the 5-character SQLSTATE (native in Postgres, where available in Oracle).
    """

    code: int = 0
    sqlstate: str = ""
    message: str = ""
    sql: str = ""
    binds: dict[str, Any] | None = None

    def __str__(self) -> str:  # pragma: no cover - trivial
        prefix = f"[{self.sqlstate}] " if self.sqlstate else ""
        if self.code:
            prefix = f"{prefix}ORA-{self.code:05d} "
        return f"{prefix}{self.message}".strip()


def wrap_dbapi_error(
    exc: DBAPIError, sql: str = "", binds: dict[str, Any] | None = None
) -> DBError:
    """Extract platform codes from the DBAPI error wrapped by SQLAlchemy.

    Works for ``oracledb.DatabaseError``, ``psycopg.Error`` and most other PEP-249 drivers.
    """
    orig = exc.orig
    code = 0
    sqlstate = ""
    message = str(orig) if orig is not None else str(exc)

    # Oracle: oracledb.DatabaseError → args[0] carries .code and .message
    if orig is not None and hasattr(orig, "args") and orig.args:
        inner = orig.args[0]
        if hasattr(inner, "code") and hasattr(inner, "message"):
            code = int(getattr(inner, "code", 0) or 0)
            message = (getattr(inner, "message", "") or "").strip()

    # Postgres (psycopg): orig.diag.sqlstate + .message_primary
    diag = getattr(orig, "diag", None) if orig is not None else None
    if diag is not None:
        sqlstate = getattr(diag, "sqlstate", "") or ""
        pg_msg = getattr(diag, "message_primary", None)
        if pg_msg:
            message = pg_msg.strip()

    # Generic sqlstate (SQLAlchemy attaches it directly for some dialects).
    if not sqlstate:
        sqlstate = getattr(exc, "code", "") or ""

    return DBError(code=code, sqlstate=sqlstate, message=message, sql=sql, binds=binds)
