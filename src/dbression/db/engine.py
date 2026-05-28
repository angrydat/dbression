"""Build SQLAlchemy engines from DBFit connection properties.

DBFit suites carry directives of the form ``DatabaseEnvironment | <name>`` (e.g. `oracle`,
`postgres`). This function maps that name + the loaded `ConnectionConfig` to the
appropriate SQLAlchemy URL.

For Oracle we additionally — if the environment variable ``DBRESSION_ORACLE_CLIENT_LIB_DIR``
is set — switch to thick mode before building the engine (InstantClient is required for
Oracle servers that reject python-oracledb's thin-mode authentication).
"""
from __future__ import annotations

import os
import threading
from typing import Any

from sqlalchemy import URL, Engine, create_engine

from dbression.db.connection import ConnectionConfig

_THICK_INIT_LOCK = threading.Lock()
_THICK_INITIALIZED = False


def _maybe_init_oracle_thick() -> None:
    global _THICK_INITIALIZED
    if _THICK_INITIALIZED:
        return
    lib_dir = os.environ.get("DBRESSION_ORACLE_CLIENT_LIB_DIR")
    if not lib_dir:
        return
    with _THICK_INIT_LOCK:
        if _THICK_INITIALIZED:
            return
        import oracledb  # noqa: PLC0415 — keep the driver import local

        oracledb.init_oracle_client(lib_dir=lib_dir)
        _THICK_INITIALIZED = True


_POSTGRES_ALIASES = {"postgres", "postgresql", "pg"}
_ORACLE_ALIASES = {"oracle"}
_MSSQL_ALIASES = {"sqlserver", "mssql", "ms-sql"}


def make_engine(environment: str, config: ConnectionConfig) -> Engine:
    """Build a SQLAlchemy engine. No autocommit — the runner manages transactions."""
    env = environment.strip().lower()
    extra: dict[str, str] = config.extra or {}

    if env in _POSTGRES_ALIASES:
        url = _build_postgres_url(config, extra)
    elif env in _ORACLE_ALIASES:
        _maybe_init_oracle_thick()
        url = _build_oracle_url(config, extra)
    elif env in _MSSQL_ALIASES:
        url = _build_mssql_url(config, extra)
    else:
        raise ValueError(f"Unknown DatabaseEnvironment: {environment!r}")

    # `future=True` is the default in 2.0; `pool_pre_ping` makes long-lived sessions
    # more robust.
    return create_engine(url, pool_pre_ping=True)


def _build_postgres_url(cfg: ConnectionConfig, extra: dict[str, str]) -> URL | str:
    if cfg.connection_string:
        cs = cfg.connection_string
        if cs.startswith("jdbc:postgresql://"):
            cs = cs[len("jdbc:postgresql://") :]
            return f"postgresql+psycopg://{cs}"
        if cs.startswith("postgresql://") or cs.startswith("postgres://"):
            scheme, _, rest = cs.partition("://")
            return f"postgresql+psycopg://{rest}"
        return cs  # caller's responsibility
    host, port = _split_host_port(cfg.service)
    return URL.create(
        drivername="postgresql+psycopg",
        username=cfg.username,
        password=cfg.password,
        host=host,
        port=port,
        database=extra.get("database"),
    )


def _build_oracle_url(cfg: ConnectionConfig, extra: dict[str, str]) -> URL | str:
    if cfg.connection_string:
        cs = cfg.connection_string
        return f"oracle+oracledb://{cfg.username or ''}:{cfg.password or ''}@" + cs.replace(
            "jdbc:oracle:thin:@", ""
        )
    # DBFit's `service` is Easy Connect: host:port/service_name
    return URL.create(
        drivername="oracle+oracledb",
        username=cfg.username,
        password=cfg.password,
        host=None,
        database=None,
        query={"dsn": cfg.service or ""},
    )


def _build_mssql_url(cfg: ConnectionConfig, extra: dict[str, str]) -> URL | str:
    """SQL Server via `pymssql` — pure-Python, no ODBC driver required."""
    if cfg.connection_string:
        return cfg.connection_string
    host, port = _split_host_port(cfg.service)
    return URL.create(
        drivername="mssql+pymssql",
        username=cfg.username,
        password=cfg.password,
        host=host,
        port=port,
        database=extra.get("database"),
    )


def _split_host_port(service: str | None) -> tuple[str | None, int | None]:
    if not service:
        return None, None
    if ":" in service:
        host, _, port_str = service.partition(":")
        # Easy Connect: `host:port/service_name` — we ignore the service_name here for
        # Oracle (this function is only called for PG / MSSQL).
        port_str = port_str.split("/", 1)[0]
        try:
            return host, int(port_str)
        except ValueError:
            return service, None
    return service, None
