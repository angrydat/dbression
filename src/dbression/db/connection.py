"""Load DBFit-compatible ``*.connection.properties`` files."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _expand_vars(value: str) -> str:
    """Replace ``${VAR}`` placeholders with ``os.environ[VAR]``.

    If a variable is missing we raise KeyError with an informative message — silently
    inserting an empty string would just hide the misconfiguration.
    """

    def repl(m: re.Match[str]) -> str:
        name = m.group(1)
        try:
            return os.environ[name]
        except KeyError as exc:
            raise KeyError(
                f"connection.properties references undefined environment variable: ${{{name}}}"
            ) from exc

    return _VAR_RE.sub(repl, value)


@dataclass(slots=True)
class ConnectionConfig:
    """DBFit-compatible connection parameters.

    Either `connection_string` (Easy Connect / TNS) OR (`service`, `username`, `password`).
    `username` / `password` are still populated when a `connection_string` is set —
    the driver decides what to use.
    """

    connection_string: str | None = None
    service: str | None = None
    username: str | None = None
    password: str | None = None
    extra: dict[str, str] | None = None


def load_connection_properties(path: Path) -> ConnectionConfig:
    """Parse a Java-style ``.properties`` file.

    Recognized keys: `connection-string`, `service`, `username`, `password`.
    Unknown keys land in `extra`. Lines starting with `#` or `!` are comments.
    """
    cfg = ConnectionConfig(extra={})
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("!"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().lower()
        value = value.strip()
        value = _expand_vars(value)
        if key == "connection-string":
            cfg.connection_string = value
        elif key == "service":
            cfg.service = value
        elif key == "username":
            cfg.username = value
        elif key == "password":
            cfg.password = value
        else:
            assert cfg.extra is not None
            cfg.extra[key] = value
    return cfg


def resolve_connection_file(declared: str, suite_root: Path) -> Path:
    """Find the actual connection.properties file on disk.

    DBFit suites often carry absolute paths from inside the container
    (``/dbfit/FitNesseRoot/...``). Strategy:

      1. If the absolute path exists, use it.
      2. Otherwise take the basename and look in `suite_root` and all of its ancestors up
         to the filesystem root.

    Raises FileNotFoundError if nothing matches.
    """
    p = Path(declared)
    if p.is_absolute() and p.exists():
        return p
    basename = p.name
    candidate = suite_root / basename
    if candidate.exists():
        return candidate
    for parent in suite_root.parents:
        candidate = parent / basename
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"connection.properties file not found — declared: {declared!r}, "
        f"searched from suite root: {suite_root}"
    )
