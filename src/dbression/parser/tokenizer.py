"""Tokenizer for the FitNesse-wiki DBFit subset.

Turns wiki source into a stream of tokens (directives, headings, table rows). Two escape
modes are honored in which pipes do NOT act as cell separators:

* FitNesse escape:     ``!- ... -!`` (may span multiple lines)
* Oracle custom quote: ``q'X ... X'`` where X is a delimiter character
  (allowed pairs: ``( )``, ``[ ]``, ``{ }``, ``< >``, otherwise char = char).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator


@dataclass(slots=True)
class Heading:
    level: int
    text: str
    line: int


@dataclass(slots=True)
class DirectiveToken:
    name: str
    value: str
    line: int


@dataclass(slots=True)
class TableRow:
    cells: list[str]
    starts_table: bool  # True if the source line started with `!|`
    line: int


Token = Heading | DirectiveToken | TableRow


_ORACLE_QUOTE_PAIRS = {"(": ")", "[": "]", "{": "}", "<": ">"}


def tokenize(text: str) -> Iterator[Token]:
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = raw.lstrip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("!|") or stripped.startswith("|"):
            logical, consumed = _read_logical_row(lines, i)
            starts_table = stripped.startswith("!|")
            body = logical[2:] if starts_table else logical[1:]
            # Drop trailing pipe (wiki tables end with `|`)
            if body.endswith("|"):
                body = body[:-1]
            cells = _split_cells(body)
            yield TableRow(cells=cells, starts_table=starts_table, line=i + 1)
            i += consumed
            continue
        if stripped.startswith("!"):
            tok = _parse_directive_or_heading(stripped, i + 1)
            if tok is not None:
                yield tok
            i += 1
            continue
        # Other markup lines (prose, !contents widget output, etc.) are ignored
        i += 1


def _read_logical_row(lines: list[str], start: int) -> tuple[str, int]:
    """Concatenate physical lines while a `!- ... -!` escape is open.

    Returns (joined text, number of consumed lines).
    """
    pieces: list[str] = []
    i = start
    escape_open = False
    while i < len(lines):
        line = lines[i]
        pieces.append(line)
        # Update escape state after consuming this line
        escape_open = _escape_state_after(line, escape_open)
        i += 1
        if not escape_open:
            break
    return "\n".join(pieces), i - start


def _escape_state_after(line: str, was_open: bool) -> bool:
    """Whether the FitNesse `!- ... -!` escape is still open after this line.

    Simple model: count unbalanced open/close markers. Does not consider Oracle quotes
    (where `!-`/`-!` could appear as literals — not observed in real-world suites; we can
    sharpen this if it ever shows up).
    """
    j = 0
    state = was_open
    while j < len(line):
        if state:
            idx = line.find("-!", j)
            if idx < 0:
                return True
            state = False
            j = idx + 2
        else:
            idx = line.find("!-", j)
            if idx < 0:
                return False
            state = True
            j = idx + 2
    return state


def _split_cells(body: str) -> list[str]:
    """Split a table row into cells.

    Pipes inside `!- ... -!` and `q'X...X'` are NOT treated as separators. Cells are
    trimmed; escape markers are removed from the cell content (the captured text is kept).
    """
    cells: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        # FitNesse escape opening?
        if c == "!" and i + 1 < n and body[i + 1] == "-":
            end = body.find("-!", i + 2)
            if end < 0:
                # Unbalanced — keep the rest as literal
                buf.append(body[i + 2 :])
                i = n
            else:
                buf.append(body[i + 2 : end])
                i = end + 2
            continue
        # Oracle quote `q'X...X'` opening?
        if (
            (c == "q" or c == "Q")
            and i + 2 < n
            and body[i + 1] == "'"
        ):
            opener = body[i + 2]
            closer = _ORACLE_QUOTE_PAIRS.get(opener, opener)
            end = body.find(closer + "'", i + 3)
            if end < 0:
                buf.append(body[i:])
                i = n
            else:
                buf.append(body[i : end + 2])
                i = end + 2
            continue
        if c == "|":
            cells.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    cells.append("".join(buf).strip())
    return cells


def _parse_directive_or_heading(stripped: str, line: int) -> Token | None:
    """Recognize `!1`/`!2`/`!3` headings, `!path`, `!define`, `!include`, `!contents`, `!note`.

    Unknown `!xxx` directives are returned as a DirectiveToken with the rest of the line
    as value, so the parser above can warn. `!contents` is dropped entirely (FitNesse widget).
    """
    # Headings: !1 / !2 / !3 / !4 / !5
    if (
        len(stripped) >= 2
        and stripped[1].isdigit()
        and (len(stripped) == 2 or stripped[2] == " " or stripped[2] == "\t")
    ):
        level = int(stripped[1])
        text = stripped[2:].strip()
        return Heading(level=level, text=text, line=line)

    # `!contents …` → ignored (FitNesse table-of-contents widget)
    if stripped.startswith("!contents"):
        return None

    # `!path <value>`
    if stripped.startswith("!path"):
        return DirectiveToken(name="path", value=stripped[len("!path") :].strip(), line=line)

    # `!define NAME {value}` or `!define NAME=value`
    if stripped.startswith("!define"):
        return DirectiveToken(name="define", value=stripped[len("!define") :].strip(), line=line)

    # `!include <path>`
    if stripped.startswith("!include"):
        return DirectiveToken(name="include", value=stripped[len("!include") :].strip(), line=line)

    # `!note …` → ignored
    if stripped.startswith("!note"):
        return None

    # Unknown — pass through as a directive
    rest = stripped[1:]
    space = rest.find(" ")
    if space < 0:
        return DirectiveToken(name=rest, value="", line=line)
    return DirectiveToken(name=rest[:space], value=rest[space + 1 :].strip(), line=line)
