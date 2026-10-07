"""pytest plugin: write each test's outcome and failure cause as JSON lines.

Loaded by testrun.py with -p factory_pytest_plugin. The file comes from FACTORY_PYTEST_REPORT.
The red check uses the cause to tell a missing unit (a valid red) from a broken test file.
"""
import json
import os

import pytest


def _write(record):
    out = os.environ.get("FACTORY_PYTEST_REPORT")
    if out:
        with open(out, "a") as stream:
            stream.write(json.dumps(record) + "\n")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" and not report.failed:
        return
    record = {"id": item.nodeid, "when": report.when, "outcome": report.outcome}
    if report.failed and call.excinfo is not None:
        error = call.excinfo.value
        record["exc"] = type(error).__name__
        record["msg"] = str(error)[:300]
        if isinstance(error, ImportError):
            record["module"] = error.name
        frames = call.excinfo.traceback
        if len(frames):
            record["file"] = os.path.relpath(str(frames[-1].path), str(item.config.rootpath))
    _write(record)


def pytest_collectreport(report):
    if report.failed:
        _write({"id": report.nodeid, "when": "collect", "outcome": "failed"})
