"""Tests for the JUnit XML and JSON reporters (structural, no live DB needed)."""
from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree as ET

from dbression.fixtures.base import FixtureResult
from dbression.report import write_json_report, write_junit_xml
from dbression.runner import PageResult, SuiteResult, TableResult


def _make_suite() -> SuiteResult:
    """Build a realistic SuiteResult without running against a DB."""
    # Top-level suite with one green + one red page test
    pass_page = PageResult(
        name="GreenTest",
        path=Path("/x/GreenTest.wiki"),
        tables=[
            TableResult(
                name="Query",
                result=FixtureResult(passed=True, message="Query OK (1 rows)"),
                duration=0.012,
            )
        ],
    )
    fail_page = PageResult(
        name="RedTest",
        path=Path("/x/RedTest.wiki"),
        tables=[
            TableResult(
                name="Query",
                result=FixtureResult(
                    passed=False, message="Row-Mismatch", details="expected 3, got 1"
                ),
                duration=0.034,
            )
        ],
    )
    # Sub-suite with a failed SetUp
    sub = SuiteResult(
        name="BrokenSub",
        setup_result=PageResult(
            name="SuiteSetUp",
            path=Path("/x/BrokenSub/SuiteSetUp.wiki"),
            tables=[
                TableResult(
                    name="Insert",
                    result=FixtureResult(
                        passed=False, message="Duplicate key", details="[23505] org_benutzer_pkey"
                    ),
                    duration=0.005,
                )
            ],
        ),
        error="SuiteSetUp failed: SuiteSetUp",
    )
    # Sub-suite that failed during engine construction
    broken_engine = SuiteResult(name="BrokenEng", error="Engine build: FileNotFoundError: x")

    return SuiteResult(
        name="root",
        pages=[pass_page, fail_page],
        subsuites=[sub, broken_engine],
    )


def test_junit_xml_structure(tmp_path: Path) -> None:
    out = tmp_path / "junit.xml"
    write_junit_xml(_make_suite(), out)
    assert out.exists()

    tree = ET.parse(out)
    root = tree.getroot()
    assert root.tag == "testsuites"
    # Aggregate counts
    assert int(root.attrib["tests"]) >= 4  # 2 root pages + 1 setup error + 1 engine error
    assert int(root.attrib["failures"]) >= 1
    assert int(root.attrib["errors"]) >= 2

    suites = root.findall("testsuite")
    suite_names = [s.attrib["name"] for s in suites]
    assert "root" in suite_names
    assert "root.BrokenSub" in suite_names
    assert "root.BrokenEng" in suite_names

    # Failure body must contain the details
    root_ts = next(s for s in suites if s.attrib["name"] == "root")
    red = next(c for c in root_ts.findall("testcase") if c.attrib["name"] == "RedTest")
    fail = red.find("failure")
    assert fail is not None
    assert "Row-Mismatch" in fail.attrib["message"]
    assert "expected 3, got 1" in (fail.text or "")


def test_json_report_structure(tmp_path: Path) -> None:
    out = tmp_path / "report.json"
    write_json_report(_make_suite(), out)
    data = json.loads(out.read_text())

    assert data["version"] == "1"
    assert data["tool"] == "dbression"
    s = data["summary"]
    assert s["tests"] == 2  # only test pages (setup / teardown are not counted)
    assert s["passed"] == 1
    assert s["failed"] == 1
    assert s["errors"] == 0

    suite = data["suite"]
    assert suite["name"] == "root"
    assert len(suite["pages"]) == 2
    assert suite["pages"][0]["passed"] is True
    assert suite["pages"][1]["passed"] is False
    assert len(suite["subsuites"]) == 2
    assert suite["subsuites"][0]["error"] == "SuiteSetUp failed: SuiteSetUp"
    assert suite["subsuites"][1]["error"].startswith("Engine build:")


def test_junit_creates_parent_dir(tmp_path: Path) -> None:
    """The ``test-reports/`` directory (Bitbucket convention) is created automatically."""
    out = tmp_path / "test-reports" / "junit.xml"
    write_junit_xml(_make_suite(), out)
    assert out.is_file()
