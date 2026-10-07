"""Check a unit's size and shape before any test runs (sizing at cut time).  Usage: unit_check.py <unit.json>

A unit is one observable behaviour: a paragraph under 100 words that names one sabotage, 3 to 5 red
tests, at most 3 code files, a named seam (the public function or command the tests call), one
out-of-scope line, and an estimate of at most 120 minutes. Anything larger is refused: cut it smaller.
"""
import json
import re
import sys
from pathlib import Path

FORBIDDEN = {"state.md", "CLAUDE.md", "AGENTS.md", "factory.toml", "factory.json"}
TEST_ID = re.compile(r"[^\s:]+\.py::test_[A-Za-z0-9_]+")
MAX_CODE_FILES, MIN_TESTS, MAX_TESTS, MAX_WORDS, MAX_MINUTES = 3, 3, 5, 100, 120


class UnitRefused(ValueError):
    """The unit breaks a size or shape rule."""


def is_test_file(name):
    return name.startswith("tests/") or Path(name).name.startswith("test_")


def check_unit(path):
    try:
        unit = json.loads(Path(path).read_text())
    except (OSError, ValueError) as error:
        raise UnitRefused(f"cannot read unit JSON: {error}") from error
    files, tests, paragraph = unit.get("files"), unit.get("tests"), unit.get("paragraph")
    if not isinstance(files, list) or not files or not all(isinstance(f, str) and f for f in files):
        raise UnitRefused("files must list file paths")
    bad = [f for f in files if f in FORBIDDEN or f.startswith(("plan/", "factory/", ".claude/", "var/"))]
    if bad:
        raise UnitRefused(f"a unit may not touch {', '.join(bad)}")
    if len([f for f in files if not is_test_file(f)]) > MAX_CODE_FILES:
        raise UnitRefused(f"a unit may name at most {MAX_CODE_FILES} code files")
    if not isinstance(tests, list) or not MIN_TESTS <= len(tests) <= MAX_TESTS:
        raise UnitRefused(f"a unit must name {MIN_TESTS} to {MAX_TESTS} tests")
    if not all(isinstance(t, str) and TEST_ID.fullmatch(t) for t in tests):
        raise UnitRefused("each test must be written file.py::test_name")
    if not isinstance(paragraph, str) or not paragraph.strip():
        raise UnitRefused("paragraph must be text")
    if len(paragraph.split()) > MAX_WORDS:
        raise UnitRefused(f"the paragraph may not exceed {MAX_WORDS} words")
    if "`" in paragraph or any("/" in w or w.endswith((".py", ".md", ".json")) for w in paragraph.split()):
        raise UnitRefused("the paragraph may not contain code or a file path")
    if "sabotage" not in paragraph.lower():
        raise UnitRefused("the paragraph must name one sabotage")
    if not isinstance(unit.get("out_of_scope"), str) or not unit["out_of_scope"].strip():
        raise UnitRefused("out_of_scope must be one line of text")
    if not isinstance(unit.get("seam"), str) or not unit["seam"].strip():
        raise UnitRefused("seam must name the public function or command the tests call")
    minutes = unit.get("estimate_minutes")
    if type(minutes) is not int or not 1 <= minutes <= MAX_MINUTES:
        raise UnitRefused(f"estimate_minutes must be a whole number from 1 to {MAX_MINUTES}; "
                          "a bigger unit is too big for one session: cut it smaller")
    if unit.get("outside_tool") and not unit.get("research"):
        raise UnitRefused("a unit about an outside tool must name its reviewed research file (research)")
    return {"ok": True, "files": len(files), "tests": len(tests), "words": len(paragraph.split())}


if __name__ == "__main__":
    try:
        print(json.dumps(check_unit(sys.argv[1])))
    except (UnitRefused, IndexError) as error:
        print(f"unit refused: {error}", file=sys.stderr)
        sys.exit(2)
