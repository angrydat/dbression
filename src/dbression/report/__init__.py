"""Reporters for SuiteResult data.

* `console`     — pytest-style rich output (default CLI output)
* `progress`    — live spinner + x/y counter + per-fixture detail lines (`--details`)
* `junit`       — JUnit XML for Bitbucket Pipelines, Jenkins, GitLab, etc.
* `json_report` — JSON for LLM tooling, custom dashboards, diff analyses
"""
from dbression.report.console import print_suite_result
from dbression.report.json_report import write_json_report
from dbression.report.junit import write_junit_xml
from dbression.report.progress import ProgressObserver, make_progress

__all__ = [
    "ProgressObserver",
    "make_progress",
    "print_suite_result",
    "write_json_report",
    "write_junit_xml",
]
