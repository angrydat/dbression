"""JUnit XML reporter — compatible with Bitbucket Pipelines, Jenkins, GitLab CI,
GitHub Actions.

Schema follows the de-facto "JUnit XML" variant (Ant / xUnit) as consumed by pytest's
``--junitxml`` and the majority of CI tooling plugins.

* Root: ``<testsuites>`` with aggregate counts
* Per dbression suite (flattened recursively): one ``<testsuite>`` with a dotted path name
* Per page: one ``<testcase>``; ``classname`` = suite path, ``name`` = page name
* Failed tests: ``<failure>`` with message + detail text as body
* Infrastructure errors (engine build, parser crash): ``<error>``
* SuiteSetUp / SuiteTearDown failures get a synthetic ``<testcase>`` with ``<error>``

Bitbucket convention: write the file to ``test-reports/<name>.xml`` — Bitbucket picks it
up automatically and renders it in the pipeline UI.
"""
from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from dbression.runner import PageResult, SuiteResult, TableResult


def write_junit_xml(suite_result: SuiteResult, path: Path | str) -> None:
    """Write the JUnit XML document to `path`."""
    root = _build_root(suite_result)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(out, encoding="utf-8", xml_declaration=True)


def _build_root(suite_result: SuiteResult) -> ET.Element:
    """Aggregate over the whole suite tree and build <testsuites>."""
    flat: list[tuple[list[str], SuiteResult]] = []
    _flatten(suite_result, [], flat)

    total_tests = 0
    total_failures = 0
    total_errors = 0
    total_time = 0.0
    testsuite_elements: list[ET.Element] = []

    for path_parts, sr in flat:
        ts_elem, t, f, e, dur = _build_testsuite(path_parts, sr)
        testsuite_elements.append(ts_elem)
        total_tests += t
        total_failures += f
        total_errors += e
        total_time += dur

    root = ET.Element(
        "testsuites",
        {
            "name": "dbression",
            "tests": str(total_tests),
            "failures": str(total_failures),
            "errors": str(total_errors),
            "time": f"{total_time:.3f}",
        },
    )
    for ts in testsuite_elements:
        root.append(ts)
    return root


def _flatten(
    sr: SuiteResult,
    path: list[str],
    out: list[tuple[list[str], SuiteResult]],
) -> None:
    """Collect all sub-suites flattened with their path prefix."""
    current_path = [*path, sr.name]
    out.append((current_path, sr))
    for sub in sr.subsuites:
        _flatten(sub, current_path, out)


def _build_testsuite(
    path_parts: list[str], sr: SuiteResult
) -> tuple[ET.Element, int, int, int, float]:
    """Build a <testsuite> for a single dbression suite (its own pages + setup/teardown).

    Pages of sub-suites are NOT listed here — they get their own <testsuite> entry.
    """
    classname = ".".join(path_parts)
    cases: list[ET.Element] = []
    failures = 0
    errors = 0
    total_time = 0.0

    # Report a SuiteSetUp failure as a synthetic testcase.
    if sr.setup_result is not None and not sr.setup_result.passed:
        dur = sum(t.duration for t in sr.setup_result.tables)
        total_time += dur
        case = _testcase_element(classname, "SuiteSetUp", dur)
        _attach_error(case, sr.setup_result)
        errors += 1
        cases.append(case)

    # Suite-level engine-build / parser errors etc.
    if sr.error and (sr.setup_result is None or sr.setup_result.passed):
        case = _testcase_element(classname, "SuiteError", 0.0)
        err = ET.SubElement(case, "error", {"message": sr.error, "type": "SuiteError"})
        err.text = sr.error
        errors += 1
        cases.append(case)

    # Page tests.
    for page in sr.pages:
        dur = sum(t.duration for t in page.tables)
        total_time += dur
        case = _testcase_element(classname, page.name, dur)
        if page.error:
            err = ET.SubElement(case, "error", {"message": page.error, "type": "PageError"})
            err.text = _build_failure_body(page)
            errors += 1
        elif not page.passed:
            failed_tbl = _first_failed_table(page)
            msg = failed_tbl.result.message if failed_tbl else "Unknown failure"
            fail_el = ET.SubElement(case, "failure", {"message": msg, "type": "AssertionError"})
            fail_el.text = _build_failure_body(page)
            failures += 1
        cases.append(case)

    # SuiteTearDown failure.
    if sr.teardown_result is not None and not sr.teardown_result.passed:
        dur = sum(t.duration for t in sr.teardown_result.tables)
        total_time += dur
        case = _testcase_element(classname, "SuiteTearDown", dur)
        _attach_error(case, sr.teardown_result)
        errors += 1
        cases.append(case)

    tests_count = len(cases)
    ts = ET.Element(
        "testsuite",
        {
            "name": classname,
            "tests": str(tests_count),
            "failures": str(failures),
            "errors": str(errors),
            "time": f"{total_time:.3f}",
        },
    )
    for c in cases:
        ts.append(c)
    return ts, tests_count, failures, errors, total_time


def _testcase_element(classname: str, name: str, dur: float) -> ET.Element:
    return ET.Element(
        "testcase",
        {"classname": classname, "name": name, "time": f"{dur:.3f}"},
    )


def _attach_error(case: ET.Element, pr: PageResult) -> None:
    failed_tbl = _first_failed_table(pr)
    msg = failed_tbl.result.message if failed_tbl else (pr.error or "unknown")
    err = ET.SubElement(case, "error", {"message": msg, "type": "AssertionError"})
    err.text = _build_failure_body(pr)


def _first_failed_table(pr: PageResult) -> TableResult | None:
    for t in pr.tables:
        if not t.result.passed:
            return t
    return None


def _build_failure_body(pr: PageResult) -> str:
    """Detail text for <failure> / <error> — contains the fixture table, the failure
    message and the details. At most as verbose as the console reporter would render.
    """
    parts: list[str] = []
    if pr.error:
        parts.append(f"Page error: {pr.error}")
    for t in pr.tables:
        if t.result.passed:
            continue
        parts.append(f"--- {t.name} ({t.duration:.3f}s) ---")
        parts.append(t.result.message)
        if t.result.details:
            parts.append(t.result.details)
    return "\n".join(parts).strip() or "(no detail)"
