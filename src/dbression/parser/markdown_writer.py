"""Render a Page AST as a ``.test.md`` file (used by ``dbression convert``)."""
from __future__ import annotations

from io import StringIO

from dbression.parser.ast import Page, Table


_SQL_FENCE_FIXTURES = {"query", "execute", "execute ddl", "store query"}


def page_to_markdown(page: Page) -> str:
    """Convert a Page (e.g. from parse_wiki()) to .test.md content."""
    out = StringIO()
    title = _humanize(page.name)
    out.write(f"# {title}\n\n")

    # Directives & tags at the top
    if page.tags:
        out.write(f"<!-- dbression:tags {', '.join(page.tags)} -->\n")

    written_env = False
    written_conn = False
    for table in page.tables:
        norm = " ".join(table.name.strip().lower().split())
        if norm == "databaseenvironment":
            val = table.header_args[0] if table.header_args else ""
            out.write(f"<!-- dbression:env={val} -->\n")
            written_env = True
            continue
        if norm == "connectusingfile":
            val = table.header_args[0] if table.header_args else ""
            out.write(f"<!-- dbression:connection={val} -->\n")
            written_conn = True
            continue
        if norm == "import fixture":
            # dbression doesn't need a Java fixture import
            continue
        break  # first real fixture table reached — bail out of the prelude

    if written_env or written_conn or page.tags:
        out.write("\n")

    for table in page.tables:
        norm = " ".join(table.name.strip().lower().split())
        if norm in {"databaseenvironment", "connectusingfile", "import fixture"}:
            continue
        _write_table(out, table, norm)

    return out.getvalue()


def _write_table(out: StringIO, table: Table, norm: str) -> None:
    fixture_display = table.name
    args = list(table.header_args)
    sql: str | None = None

    # If this fixture typically carries SQL as its first arg, lift it into a ```sql fence.
    if norm in _SQL_FENCE_FIXTURES and args:
        sql = args[0]
        args = args[1:]

    h3 = fixture_display
    if args:
        h3 += " " + " ".join(args)
    out.write(f"### {h3}\n\n")

    if sql is not None:
        out.write("```sql\n")
        out.write(sql.strip() + "\n")
        out.write("```\n\n")

    if table.headers:
        out.write("| " + " | ".join(table.headers) + " |\n")
        out.write("|" + "|".join("---" for _ in table.headers) + "|\n")
        for row in table.rows:
            padded = row + [""] * (len(table.headers) - len(row))
            out.write("| " + " | ".join(padded[: len(table.headers)]) + " |\n")
        out.write("\n")


def _humanize(name: str) -> str:
    """`MerklisteSuite_Test_AAdd` → "MerklisteSuite Test AAdd"."""
    return name.replace("_", " ").strip()
