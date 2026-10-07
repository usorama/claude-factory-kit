"""Build check: only listed files changed, test files unchanged, named tests pass, every new check
is protected by a named test (guard), and the whole suite passes apart from other units' tests.
Usage: build_check.py <unit.json> <base commit>
"""
import json
import sys
from pathlib import Path

from common import git
from guard import survivors
from testrun import base_id, failed, run
from unit_check import is_test_file


class BuildCheckRefused(ValueError):
    """The finished unit does not meet its build checks."""


def changed_files(worktree, base):
    changed = set(git(worktree, "diff", "--name-only", base).stdout.split())
    return changed | set(git(worktree, "ls-files", "--others", "--exclude-standard").stdout.split())


def build_check(unit_path, worktree, base, tolerated=(), guard=True, suite=True):
    worktree = Path(worktree)
    unit = json.loads((worktree / unit_path).read_text())
    names = unit["tests"]
    test_files = {name.split("::")[0] for name in names}
    changed = changed_files(worktree, base)
    for path in sorted(changed):
        if path not in set(unit["files"]) | test_files:
            raise BuildCheckRefused(f"{path} is outside the file list")
    for path in sorted(test_files | {f for f in unit["files"] if is_test_file(f)}):
        if path in changed:
            raise BuildCheckRefused(f"{path} changed; tests are fixed at the cut")
    _, records, _, _ = run(worktree, names)
    for name in names:
        if records.get(name, {}).get("outcome") != "passed":
            raise BuildCheckRefused(f"{name} still fails")
    result = {"ok": True, "files_changed": sorted(changed), "tests": len(names)}
    if guard:
        code_files = [f for f in unit["files"] if f.endswith(".py") and not is_test_file(f)
                      and (worktree / f).is_file()]
        report = survivors(worktree, base, code_files, names)
        if report["survivors"]:
            raise BuildCheckRefused(f"{report['survivors'][0]}: no named test fails when this check is removed")
        result["guard"] = report
    if suite:
        _, records, collect_errors, _ = run(worktree)
        if collect_errors:
            raise BuildCheckRefused(f"{collect_errors[0]} fails at collection")
        outside = [t for t in failed(records) if base_id(t) not in set(tolerated)]
        if outside:
            raise BuildCheckRefused(f"{outside[0]} fails outside the unit")
        result["suite_passed"] = sum(r["outcome"] == "passed" for r in records.values())
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(build_check(sys.argv[1], Path.cwd(), sys.argv[2])))
    except (BuildCheckRefused, IndexError) as error:
        print(f"build check refused: {error}", file=sys.stderr)
        sys.exit(2)
