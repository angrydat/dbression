"""Symbol table and substitution mechanics.

DBFit conventions:

* ``>>name`` in an output column of a ``Query`` captures the value of the first result row
  into the symbol ``name``.
* ``<<name`` in an input cell is replaced with the symbol value before execution.
* SQL statements use Oracle bind syntax ``:name`` — the adapter extracts the required bind
  names and fills them from the symbol table.
* ``!define NAME VALUE`` sets a static variable; this also ends up in the symbol table.
"""
from __future__ import annotations

import re
from typing import Any

_BIND_RE = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")
_CELL_READ_RE = re.compile(r"<<([A-Za-z_][A-Za-z0-9_]*)")
_SQL_TEXT_SUBST_RE = re.compile(r"_:([A-Za-z_][A-Za-z0-9_]*)")


class SymbolTable:
    """Key → value. Values may be any Python object (str, int, Decimal, datetime, …)."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def set(self, name: str, value: Any) -> None:
        self._data[name] = value

    def get(self, name: str) -> Any:
        try:
            return self._data[name]
        except KeyError as exc:
            raise KeyError(f"Symbol not defined: {name!r}") from exc

    def has(self, name: str) -> bool:
        return name in self._data

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._data

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)


def substitute_sql_text(sql: str, symbols: SymbolTable) -> str:
    """Replace ``_:name`` with the symbol value as literal SQL text (DBFit convention).

    Distinction:
    * ``_:name`` → text substitution: the symbol value is inserted as a literal before
      compile. Needed where SQL expects a cast or operator immediately
      (e.g. ``_:id::int`` or ``_:tag::text``).
    * ``:name``  → bind parameter (handled natively by SQLAlchemy/driver).
    """

    def repl(m: re.Match[str]) -> str:
        name = m.group(1)
        if not symbols.has(name):
            raise KeyError(f"SQL text substitution references undefined symbol: _:{name}")
        return str(symbols.get(name))

    return _SQL_TEXT_SUBST_RE.sub(repl, sql)


def substitute_cell(cell: str, symbols: SymbolTable) -> str:
    """Replace ``<<name`` occurrences in a cell with the corresponding symbol values
    (rendered as strings).

    Unknown symbols raise KeyError with an informative message.
    """

    def repl(m: re.Match[str]) -> str:
        name = m.group(1)
        if not symbols.has(name):
            raise KeyError(f"Cell references undefined symbol: <<{name}")
        return str(symbols.get(name))

    return _CELL_READ_RE.sub(repl, cell)


def extract_binds(sql: str) -> list[str]:
    """Return the bind names (``:name``) used in a SQL statement, in order of first
    appearance, with duplicates removed.

    Heuristic: ``:name`` occurrences inside single-quoted strings or Oracle custom-quoted
    strings are ignored by replacing those literals with placeholders before scanning.
    """
    cleaned = _strip_string_literals(sql)
    seen: list[str] = []
    for m in _BIND_RE.finditer(cleaned):
        n = m.group(1)
        if n not in seen:
            seen.append(n)
    return seen


def _strip_string_literals(sql: str) -> str:
    """Replace everything inside ``'…'`` and ``q'X…X'`` with spaces of equal length so
    that the original indexing is preserved.
    """
    out: list[str] = []
    i = 0
    n = len(sql)
    pairs = {"(": ")", "[": "]", "{": "}", "<": ">"}
    while i < n:
        c = sql[i]
        if (c == "q" or c == "Q") and i + 2 < n and sql[i + 1] == "'":
            opener = sql[i + 2]
            closer = pairs.get(opener, opener) + "'"
            end = sql.find(closer, i + 3)
            if end < 0:
                out.append(" " * (n - i))
                i = n
            else:
                out.append(" " * (end + 2 - i))
                i = end + 2
            continue
        if c == "'":
            end = sql.find("'", i + 1)
            # Naive: we ignore doubled single-quotes as an escape sequence here because
            # bind extraction stays correct even in the imprecise case, as long as `:name`
            # never appears inside a string literal.
            if end < 0:
                out.append(" " * (n - i))
                i = n
            else:
                out.append(" " * (end + 1 - i))
                i = end + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def bind_values(names: list[str], symbols: SymbolTable) -> dict[str, Any]:
    """Return a dict {name: value} from the symbol table for the requested bind names."""
    return {n: symbols.get(n) for n in names}
