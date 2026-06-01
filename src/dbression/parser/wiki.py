"""Wiki parser: token stream → AST (Page / Suite)."""
from __future__ import annotations

from pathlib import Path

from dbression.parser.ast import Directive, Page, Suite, Table
from dbression.parser.tokenizer import DirectiveToken, Heading, TableRow, tokenize


# Known fixture names (lowercased + space-normalized) that — when they appear as the
# first cell of a plain `|…|` row — start a new table even without the `!` prefix.
# DBFit wiki files are inconsistent here; the Java parser likewise ends a table whenever
# a registered fixture appears as the first token.
_TABLE_STARTER_FIXTURES = {
    "query",
    "ordered query",
    "execute",
    "execute ddl",
    "execute procedure",
    "execute procedure expect exception",
    "insert",
    "update",
    "delete",
    "set parameter",
    "set option",
    "databaseenvironment",
    "connectusingfile",
    "import fixture",
    "store query",
    "compare stored queries",
    "inspect procedure",
    "inspect table",
    "inspect view",
    "store query",
    "compare stored queries",
}


def _extract_front_matter(text: str) -> tuple[list[str], str]:
    """Read the YAML-style front-matter block at the top of the file.

    Recognized:

    ```
    ---
    Suites: critical
    ---
    ```

    Multiple values may be separated by commas or whitespace. Currently only the
    ``Suites:`` key is evaluated — everything else is ignored. Returns (tags, remaining body).
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return [], text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return [], text
    tags: list[str] = []
    for raw in lines[1:end]:
        line = raw.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        if key.strip().lower() == "suites":
            for chunk in value.replace(",", " ").split():
                if chunk and chunk not in tags:
                    tags.append(chunk)
    body = "\n".join(lines[end + 1 :])
    return tags, body


def _is_table_starter(cells: list[str]) -> bool:
    if not cells:
        return False
    name = " ".join(cells[0].strip().lower().split())
    return name in _TABLE_STARTER_FIXTURES


def parse_wiki(path: Path) -> Page:
    """Parse a single ``.wiki`` file into a Page."""
    text = path.read_text(encoding="utf-8")
    tags, body = _extract_front_matter(text)
    page = Page(path=path, name=path.stem, tags=tags)
    tokens = list(tokenize(body))
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if isinstance(tok, DirectiveToken):
            page.directives.append(Directive(name=tok.name, value=tok.value, line=tok.line))
            i += 1
            continue
        if isinstance(tok, Heading):
            i += 1
            continue
        if isinstance(tok, TableRow):
            # Skip if the row neither starts with `!|` nor begins with a known fixture name
            # (e.g. stray table fragments outside any recognizable fixture).
            if not tok.starts_table and not _is_table_starter(tok.cells):
                i += 1
                continue
            table, consumed = _parse_table(tokens, i)
            page.tables.append(table)
            i += consumed
            continue
        i += 1
    return page


def _parse_table(tokens: list, start: int) -> tuple[Table, int]:
    """Read a Table starting at tokens[start] (a TableRow with starts_table=True).

    A Table consists of the start row (fixture name + optional arguments) plus subsequent
    consecutive TableRows with starts_table=False. Heading or Directive tokens end the
    table. An optional header row (column names) follows as the second row.
    """
    head = tokens[start]
    assert isinstance(head, TableRow)
    # Some real-world wikis use `|…|` rows without a preceding `!|…|` — we accept those
    # as ad-hoc tables. The fixture name then comes from the first cell as usual.
    name = head.cells[0] if head.cells else ""
    header_args = head.cells[1:] if len(head.cells) > 1 else []

    body_rows: list[list[str]] = []
    i = start + 1
    while i < len(tokens):
        nxt = tokens[i]
        if not isinstance(nxt, TableRow):
            break
        # A new table starts at `!|` OR at a known fixture name in the first cell —
        # end the current table in either case.
        if nxt.starts_table or _is_table_starter(nxt.cells):
            break
        body_rows.append(nxt.cells)
        i += 1

    # First body row becomes the column headers if present
    headers: list[str] = []
    data_rows: list[list[str]] = []
    if body_rows:
        headers = body_rows[0]
        data_rows = body_rows[1:]

    table = Table(
        name=name,
        header_args=header_args,
        headers=headers,
        rows=data_rows,
        line=head.line,
    )
    return table, i - start


def parse_suite(root: Path) -> Suite:
    """Parse a suite directory recursively. Accepts both formats:

    * ``*.wiki``        — classic DBFit wiki
    * ``*.test.md``     — dbression's own format (Markdown with conventions)

    When both formats exist for the same page name, ``.test.md`` wins (newer format).
    """
    if not root.is_dir():
        raise ValueError(f"Suite path is not a directory: {root}")
    from dbression.parser.markdown import parse_markdown

    suite = Suite(root=root, name=root.name)
    # Collect all files first, then dedupe by page name (md > wiki).
    entries = sorted(root.iterdir())
    by_pagename: dict[str, tuple[Path, str]] = {}  # page-name → (path, fmt)
    for entry in entries:
        if entry.is_dir():
            if entry.name.startswith(".") or entry.name == "__pycache__":
                continue
            suite.subsuites.append(parse_suite(entry))
            continue
        # Markdown format: `.test.md`. Convention like Jest/Vitest — every `.test.md`
        # inside a suite directory is a test page.
        from dbression.parser.markdown import MARKDOWN_TEST_SUFFIX

        if entry.name.endswith(MARKDOWN_TEST_SUFFIX):
            pn = entry.name[: -len(MARKDOWN_TEST_SUFFIX)]
            by_pagename[pn] = (entry, "md")
            continue
        if entry.suffix == ".wiki":
            pn = entry.stem
            # Only register if no .md version already claimed this page name.
            by_pagename.setdefault(pn, (entry, "wiki"))

    for pn, (path, fmt) in by_pagename.items():
        page = parse_markdown(path) if fmt == "md" else parse_wiki(path)
        if pn == "_root":
            suite.root_page = page
        elif pn == "SuiteSetUp":
            suite.setup = page
        elif pn == "SuiteTearDown":
            suite.teardown = page
        else:
            suite.pages.append(page)
    # Stable, deterministic order of test pages (alphabetical).
    suite.pages.sort(key=lambda p: p.name)
    return suite
