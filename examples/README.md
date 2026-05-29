# dbression examples

Tiny, self-contained `.test.md` suites that double as living documentation for
dbression's Markdown format. Each example renders nicely on GitHub — open any
file and you can read it as prose, then run it as a test.

| Example | What it shows |
|---|---|
| [`01-hello/`](01-hello/) | The smallest possible test: a single `Query` |
| [`02-stored-procedure/`](02-stored-procedure/) | `Insert` → `Execute Procedure` → `Query`, with `>>capture` and `<<read` |
| [`03-schema-drift/`](03-schema-drift/) | `Inspect Table` as a guard against unintended schema changes |

## Running

Every example needs a working `connection.properties` next to its `_root.wiki`
(point it at any Postgres for the first two; the schema-drift demo expects a
specific table — see that example's README).

```bash
# Quickstart against your own Postgres:
export POSTGRES_PASSWORD=...
dbression run examples/01-hello/
```
