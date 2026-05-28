"""JSON reporter — richer than JUnit XML, intended for programmatic consumption
(LLM tooling, custom dashboards, diff analyses).

Top-level schema:

```json
{
  "version": "1",
  "tool": "dbression",
  "tool_version": "0.1.0",
  "summary": {"tests": N, "passed": N, "failed": N, "errors": N, "duration_seconds": T},
  "suite": <suite-node>
}
```

`<suite-node>`:

```json
{
  "name": "...",
  "error": null | "..." ,
  "setup": <page-node> | null,
  "pages": [<page-node>, ...],
  "subsuites": [<suite-node>, ...],
  "teardown": <page-node> | null
}
```

`<page-node>`:

```json
{
  "name": "...",
  "path": "...",
  "passed": true|false,
  "error": null | "...",
  "duration_seconds": T,
  "tables": [
    {
      "name": "Query",
      "passed": true|false,
      "duration_seconds": T,
      "message": "...",
      "details": "..." | ""
    }
  ]
}
```
"""
from __future__ import annotations

import json
from pathlib import Path

from dbression import __version__
from dbression.runner import PageResult, SuiteResult


def write_json_report(suite_result: SuiteResult, path: Path | str) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    data = build_report_data(suite_result)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def build_report_data(suite_result: SuiteResult) -> dict:
    """Top-level dict — also usable directly by in-memory consumers."""
    flat: list[PageResult] = []
    _collect_pages(suite_result, flat)

    total = len(flat)
    passed = sum(1 for p in flat if p.passed)
    failed = sum(1 for p in flat if not p.passed and not p.error)
    errored = sum(1 for p in flat if p.error)
    duration = sum(sum(t.duration for t in p.tables) for p in flat)

    return {
        "version": "1",
        "tool": "dbression",
        "tool_version": __version__,
        "summary": {
            "tests": total,
            "passed": passed,
            "failed": failed,
            "errors": errored,
            "duration_seconds": round(duration, 6),
        },
        "suite": _suite_node(suite_result),
    }


def _suite_node(sr: SuiteResult) -> dict:
    return {
        "name": sr.name,
        "error": sr.error,
        "setup": _page_node(sr.setup_result) if sr.setup_result else None,
        "pages": [_page_node(p) for p in sr.pages],
        "subsuites": [_suite_node(s) for s in sr.subsuites],
        "teardown": _page_node(sr.teardown_result) if sr.teardown_result else None,
    }


def _page_node(pr: PageResult) -> dict:
    return {
        "name": pr.name,
        "path": str(pr.path),
        "passed": pr.passed,
        "error": pr.error,
        "duration_seconds": round(sum(t.duration for t in pr.tables), 6),
        "tables": [
            {
                "name": t.name,
                "passed": t.result.passed,
                "duration_seconds": round(t.duration, 6),
                "message": t.result.message,
                "details": t.result.details,
            }
            for t in pr.tables
        ],
    }


def _collect_pages(sr: SuiteResult, out: list[PageResult]) -> None:
    out.extend(sr.pages)
    for sub in sr.subsuites:
        _collect_pages(sub, out)
