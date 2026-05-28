"""Markdown parser for ``.test.md`` files.

Conventions (dbression's own format — renders cleanly in any Markdown viewer):

```markdown
# My Test Suite              ← H1 = suite/page name (informational, not parsed)

<!-- dbression:env=postgres -->                ← equivalent to !|DatabaseEnvironment|postgres|
<!-- dbression:connection=conn.properties -->  ← equivalent to !|ConnectUsingFile|...|
<!-- dbression:tags critical, NotOnCI -->      ← suite tags (like YAML front-matter in wiki)
<!-- dbression:define wlk_id 42 -->            ← symbol definition

## Setup                     ← suite setup block (equivalent to SuiteSetUp.test.md)
## Teardown
## Test: My first test       ← starts a test page (the "Test: " prefix is optional)

### Query                    ← fixture: SQL comes from the next ```sql fence
​```sql
select 1 as n
​```

| n |
|---|
| 1 |

### Insert wlk.org_benutzer  ← fixture with arg(s) in the H3; data from the MD table
| wlv_user | kompetenz |
|----------|-----------|
| dbfit    | 62        |

### Execute Procedure Expect Exception pr_set_status 23505
| pBenutzer | pStatus     | pOid |
|-----------|-------------|------|
| dbfit     | Bearbeitung | <<id |
```

The parser produces the SAME Page/Table AST as the wiki parser — runner and fixture layers
need no changes. Ambiguities in the H3 line are resolved by longest-prefix match against
the fixture registry.
"""
from __future__ import annotations

import re
from pathlib import Path

from markdown_it import MarkdownIt

from dbression.parser.ast import Directive, Page, Table


_DIRECTIVE_COMMENT_RE = re.compile(
    r"<!--\s*dbression:\s*(?P<body>.+?)\s*-->",
    flags=re.DOTALL,
)


# All known fixture names (lowercased + space-normalized), sorted by descending length
# for longest-prefix matching.
_FIXTURE_NAMES_CACHE: list[tuple[str, str]] | None = None  # (normalized, original)


def _known_fixture_names() -> list[tuple[str, str]]:
    global _FIXTURE_NAMES_CACHE
    if _FIXTURE_NAMES_CACHE is None:
        from dbression.fixtures import REGISTRY

        # REGISTRY keys are already normalized; we want the originally registered display
        # name from cls.name.
        seen: dict[str, str] = {}
        for normalized, cls in REGISTRY.items():
            seen.setdefault(normalized, cls.name or normalized)
        _FIXTURE_NAMES_CACHE = sorted(
            seen.items(), key=lambda x: len(x[0]), reverse=True
        )
    return _FIXTURE_NAMES_CACHE


def parse_markdown(path: Path) -> Page:
    """Parse a ``.test.md`` file into a Page (same AST as the wiki parser).

    A `.test.md` file may contain multiple ``## Test:`` pages, but we map them to a SINGLE
    Page with all tables (wiki-compatible model: one Page per file). Setup / teardown
    sections are distinguished by filename (`SuiteSetUp.test.md` etc.); within a test page,
    ``## Test:`` headings are merely informational structure.
    """
    text = path.read_text(encoding="utf-8")
    page = Page(path=path, name=_page_name_from_path(path))

    _extract_directives_into_page(text, page)

    md = MarkdownIt("commonmark").enable("table")
    tokens = md.parse(text)
    page.tables.extend(_extract_tables(tokens))
    return page


#: File-name suffix for dbression test markdown. Convention like Jest/Vitest
#: (`*.test.ts`): inside a test directory, every ``*.test.md`` file is a test page.
MARKDOWN_TEST_SUFFIX: str = ".test.md"


def _page_name_from_path(path: Path) -> str:
    name = path.name
    if name.endswith(MARKDOWN_TEST_SUFFIX):
        return name[: -len(MARKDOWN_TEST_SUFFIX)]
    return path.stem


# ─────────────────────────────────────────────────────────────────────────────
# Directives via <!-- dbression:... -->
# ─────────────────────────────────────────────────────────────────────────────


def _extract_directives_into_page(text: str, page: Page) -> None:
    """Read every ``<!-- dbression:... -->`` comment and translate it into:

    * Tags                → page.tags
    * env= / connection=  → pseudo-table (DatabaseEnvironment / ConnectUsingFile), so the
                            runner's scanner works without a special case
    * define <name> <val> → Directive in the AST (future use)
    * import=...          → page.directives (informational)
    """
    for line_no, m in enumerate(_DIRECTIVE_COMMENT_RE.finditer(text), start=1):
        body = m.group("body").strip()
        if not body:
            continue
        # Form: "tags critical, NotOnCI"  /  "env=postgres"  /  "connection=foo.properties"
        if body.startswith("tags"):
            rest = body[len("tags") :].strip().lstrip(":=").strip()
            for chunk in rest.replace(",", " ").split():
                if chunk and chunk not in page.tags:
                    page.tags.append(chunk)
            continue
        if body.startswith("define"):
            rest = body[len("define") :].strip()
            page.directives.append(Directive(name="define", value=rest, line=line_no))
            continue
        key, _, value = body.partition("=")
        key = key.strip().lower()
        value = value.strip()
        if key in ("env", "database", "databaseenvironment"):
            page.tables.append(Table(name="DatabaseEnvironment", header_args=[value]))
        elif key in ("connection", "connectusingfile"):
            page.tables.append(Table(name="ConnectUsingFile", header_args=[value]))
        elif key == "import":
            page.directives.append(Directive(name="import", value=value, line=line_no))
        else:
            page.directives.append(Directive(name=key, value=value, line=line_no))


# ─────────────────────────────────────────────────────────────────────────────
# Token → Tables
# ─────────────────────────────────────────────────────────────────────────────


def _extract_tables(tokens: list) -> list[Table]:
    """Walk markdown-it tokens, build a fixture Table from each ``### …`` block + follow-up.

    After each H3, collect:
    * the first ``code_block`` / ``fence`` (any language) as the SQL header arg
    * the first Markdown table as column headers + data rows

    Stops at the next H1/H2/H3 heading or EOF.
    """
    tables: list[Table] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open" and tok.tag == "h3":
            # Pull the H3 text from the inline token
            inline = tokens[i + 1] if i + 1 < len(tokens) else None
            heading_text = inline.content.strip() if inline and inline.type == "inline" else ""
            i += 1  # consume inline
            # Walk until the next heading: collect first fence + first table
            j = i + 1
            sql_arg: str | None = None
            md_headers: list[str] = []
            md_rows: list[list[str]] = []
            while j < len(tokens):
                t = tokens[j]
                if t.type == "heading_open":
                    break
                if t.type == "fence" and sql_arg is None:
                    sql_arg = t.content.rstrip("\n")
                if t.type == "table_open":
                    md_headers, md_rows, j = _consume_table(tokens, j)
                    continue
                j += 1
            table = _build_table(heading_text, sql_arg, md_headers, md_rows)
            tables.append(table)
            i = j
            continue
        i += 1
    return tables


def _consume_table(tokens: list, start: int) -> tuple[list[str], list[list[str]], int]:
    """Consume a markdown-it table starting at `start` (table_open).

    Returns (headers, rows, new token index past table_close).
    """
    headers: list[str] = []
    rows: list[list[str]] = []
    current_row: list[str] | None = None
    in_header = False
    i = start
    while i < len(tokens):
        t = tokens[i]
        if t.type == "thead_open":
            in_header = True
        elif t.type == "thead_close":
            in_header = False
        elif t.type == "tr_open":
            current_row = []
        elif t.type == "tr_close":
            if current_row is not None:
                if in_header:
                    headers = current_row
                else:
                    rows.append(current_row)
            current_row = None
        elif t.type == "inline" and current_row is not None:
            current_row.append(t.content.strip())
        elif t.type == "table_close":
            return headers, rows, i + 1
        i += 1
    return headers, rows, i


# ─────────────────────────────────────────────────────────────────────────────
# H3 → fixture name + args (longest-prefix-match)
# ─────────────────────────────────────────────────────────────────────────────


def _split_fixture_and_args(heading: str) -> tuple[str, list[str]]:
    """Find the longest registered fixture name that is a prefix of `heading`.

    The remaining text is whitespace-split and returned as the args list.
    """
    normalized = " ".join(heading.strip().lower().split())
    for fname_norm, fname_orig in _known_fixture_names():
        if normalized == fname_norm:
            return fname_orig, []
        if normalized.startswith(fname_norm + " "):
            rest = heading.strip()[len(fname_orig) :].strip()
            args = rest.split() if rest else []
            return fname_orig, args
    # Fallback: the first word is the fixture name
    parts = heading.strip().split(maxsplit=1)
    if not parts:
        return "", []
    rest_args = parts[1].split() if len(parts) > 1 else []
    return parts[0], rest_args


def _build_table(
    heading: str,
    sql_arg: str | None,
    md_headers: list[str],
    md_rows: list[list[str]],
) -> Table:
    fixture_name, args = _split_fixture_and_args(heading)
    header_args: list[str] = []
    # H3 args go first (e.g. table name for Insert, procedure name for Execute Procedure)
    header_args.extend(args)
    # The SQL fence (if present and the fixture likely needs it) is added as an additional
    # header_arg. Convention: for Query/Execute/Execute Ddl/Store Query the SQL is usually
    # the FIRST header_arg in the wiki schema, so prepend rather than append.
    if sql_arg is not None:
        norm = " ".join(fixture_name.strip().lower().split())
        if norm in {"query", "execute", "execute ddl", "store query"}:
            header_args.insert(0, sql_arg)
        else:
            header_args.append(sql_arg)
    return Table(
        name=fixture_name,
        header_args=header_args,
        headers=md_headers,
        rows=md_rows,
        line=0,
    )
