"""Find file paths a brief cites, and refuse when one cannot be read (defect type 10).

A runtime file (anything under var/) never exists in a unit's work folder, so a brief must
name it in words ("the factory queue file"), never by its path.
"""
import re
from pathlib import Path

PATH = re.compile(r"(?<![\w./~-])(?:~/|/|[\w.-]+/)(?:[\w.-]+/)*[\w.-]+\.(?:jsonl|json|md|py|txt|toml|yaml|yml)\b")


def cited_paths(text):
    return [match.group() for match in PATH.finditer(text)]


def first_problem(text, root, excluded=()):
    """Return a plain reason for the first bad citation, or None."""
    for name in cited_paths(text):
        if name in excluded:
            continue
        if name.startswith("var/") or "/var/factory/" in name:
            return f"the brief cites the runtime file {name} by its path; name it in words instead"
        path = Path.home() / name[2:] if name.startswith("~/") else Path(name)
        if not path.is_absolute():
            path = Path(root) / path
        if not path.is_file():
            return f"the brief cites {name}, which is not readable on this machine"
    return None
