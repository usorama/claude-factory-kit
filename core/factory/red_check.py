"""Red check: the unit's tests fail for the right reason, and everything else passes.

Refuses (stops the unit as cut_refused):
- a bad unit shape; a brief without its eight sections, named test or named sabotage, or one
  that cites a missing or runtime file;
- a named test that passes, is missing, or fails at collection;
- a named test broken by its own test file: a fixture error, a NameError in the test file, or an
  import of a module that is not one of the unit's files;
- any other failing test, except the tests of other units still in the queue: active units, units
  with an open pull request, and
  stopped units whose stop card is open. Matching is by exact test id.
"""
import json
import re
import sys
from pathlib import Path

from brief_check import BriefRefused, check_brief
from cited_sources import first_problem
from research_check import ResearchRefused, check_research
from common import ACTIVE, STOPPED, key, label, load_unit, read_queue, var
from testrun import NETWORK_ISOLATION, base_id, failed, run
from unit_check import UnitRefused, check_unit


class RedCheckRefused(ValueError):
    """The unit cannot start from this test state."""


def tolerated_tests(root, own=None):
    """Test ids named by other units that are moving, or stopped with an open card."""
    asks = var(root) / "asks"
    names = set()
    for entry in read_queue(root)["units"]:
        if own is not None and key(entry) == key(own):
            continue
        state = entry["state"]
        if state in ACTIVE + ("pr_open",) or entry.get("hold") or (state in STOPPED and (asks / f"{label(entry['unit'])}.md").exists()):
            try:
                names.update(load_unit(entry["worktree"], entry["unit"], root)["tests"])
            except (OSError, ValueError):
                continue
    return names


def _unit_modules(unit, worktree):
    modules = set()
    for name in unit["files"]:
        if name.endswith(".py"):
            parts = name[:-3].split("/")
            modules.update(".".join(parts[i:]) for i in range(len(parts)))
            for i in range(1, len(parts)):  # a package folder the unit creates
                if not (Path(worktree) / "/".join(parts[:i])).exists():
                    modules.add(".".join(parts[:i]))
    return modules


def wrong_reason(record, unit, worktree):
    """Why a red test is red for the wrong reason, or None when the red is valid."""
    name = record["id"].split("::")[-1]
    test_file = record["id"].split("::")[0]
    if record["when"] == "setup":
        return f"{name} fails in its fixture ({record.get('exc')}), not in the unit's code"
    module = record.get("module")
    if record.get("exc") in ("ImportError", "ModuleNotFoundError") and module is not None:
        if module not in _unit_modules(unit, worktree):
            return f"{name} fails importing {module}, which is not the unit's own module"
        return None
    if record.get("exc") == "NameError" and record.get("file") == test_file:
        return f"{name} fails on a NameError in the test file itself"
    return None


def red_check(unit_path, worktree, tolerated=()):
    worktree = Path(worktree)
    unit_file = worktree / unit_path  # an absolute unit_path stays absolute
    try:
        check_unit(unit_file)
    except UnitRefused as error:
        raise RedCheckRefused(str(error)) from error
    unit = json.loads(unit_file.read_text())
    names = unit["tests"]
    brief = worktree / ".ai/specs" / f"{unit['row']}-U{unit['n']}.md"
    if not brief.is_file():
        raise RedCheckRefused(f"brief missing: .ai/specs/{brief.name}")
    try:
        check_brief(brief.read_text(), unit)
    except BriefRefused as error:
        raise RedCheckRefused(str(error)) from error
    if unit.get("outside_tool"):
        research = worktree / unit["research"]
        try:
            text = research.read_text()
            check_research(text)
        except (OSError, ResearchRefused) as error:
            raise RedCheckRefused(f"research first: {unit['research']} is missing or incomplete ({error})") from error
        if not re.search(r"^Reviewed-by: .+ PASS$", text, re.MULTILINE):
            raise RedCheckRefused(f"research first: {unit['research']} has no 'Reviewed-by: <model> PASS' line")
    problem = first_problem(brief.read_text(), worktree,
                            excluded=set(unit["files"]) | {n.split("::")[0] for n in names})
    if problem:
        raise RedCheckRefused(problem)
    _, records, collect_errors, _ = run(worktree, names)
    for name in names:
        record = records.get(name)
        if record is None:
            raise RedCheckRefused(f"{name} not found or failed at collection")
        if record["outcome"] == "passed":
            raise RedCheckRefused(f"{name} already passes")
        reason = wrong_reason(record, unit, worktree)
        if reason:
            raise RedCheckRefused(reason)
    allowed = set(names) | set(tolerated)
    code, records, collect_errors, output = run(worktree)
    if collect_errors:
        raise RedCheckRefused(f"{collect_errors[0]} fails at collection")
    outside = [t for t in failed(records) if base_id(t) not in allowed]
    if outside:
        raise RedCheckRefused(f"{outside[0]} failed outside the unit")
    if code not in (0, 1):
        raise RedCheckRefused(f"the suite could not run: {output.strip()[-300:]}")
    return {"ok": True, "red": len(names), "tolerated_red": len(set(failed(records)) - set(names)),
            "suite_passed": sum(r["outcome"] == "passed" for r in records.values()),
            "network_isolation": NETWORK_ISOLATION}


if __name__ == "__main__":
    try:
        print(json.dumps(red_check(sys.argv[1], Path.cwd())))
    except (RedCheckRefused, ValueError, IndexError) as error:
        print(f"red check refused: {error}", file=sys.stderr)
        sys.exit(2)
