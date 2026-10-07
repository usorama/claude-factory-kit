"""Check a unit's brief: the eight numbered sections, a named test from the unit's own list, and a
named sabotage. The red check runs this before any test.  Usage: brief_check.py <brief.md> <unit.json>
"""
import json
import re
import sys
from pathlib import Path

SECTIONS = 8


class BriefRefused(ValueError):
    """The brief is missing a required part."""


def check_brief(text, unit):
    numbers = [int(n) for n in re.findall(r"^## (\d+)\.", text, re.MULTILINE)]
    missing = [n for n in range(1, SECTIONS + 1) if n not in numbers]
    if missing:
        raise BriefRefused(f"the brief lacks section(s) {', '.join(map(str, missing))} of {SECTIONS}")
    named = re.search(r"^- Named test:\s*(\S+)", text, re.MULTILINE)
    if not named:
        raise BriefRefused("the brief names no test ('- Named test: <file.py::test_name>')")
    if named.group(1).strip("`") not in unit["tests"]:
        raise BriefRefused(f"the named test {named.group(1)} is not one of the unit's tests")
    sabotage = re.search(r"^- Named sabotage:\s*(\S.*)$", text, re.MULTILINE)
    if not sabotage or len(sabotage.group(1).split()) < 3:
        raise BriefRefused("the brief names no sabotage ('- Named sabotage: <what to break, which test goes red>')")
    return {"ok": True, "named_test": named.group(1).strip("`")}


if __name__ == "__main__":
    try:
        print(json.dumps(check_brief(Path(sys.argv[1]).read_text(), json.loads(Path(sys.argv[2]).read_text()))))
    except (BriefRefused, IndexError, OSError, ValueError) as error:
        print(f"brief refused: {error}", file=sys.stderr)
        sys.exit(2)
