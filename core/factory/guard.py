"""Mutation guard: remove each new check one at a time; a named test must then fail.

A check is an `if` whose body starts with `raise` or `return`. Each check is replaced by False,
and each part of an `or` chain is removed on its own. Only checks on lines the unit added count.
A mutant that keeps every named test green "survives": no test protects that check (defect 4).
A check enforced elsewhere may carry `# covered: <where>` on its `if` line; the reviewer judges it.
Usage: guard.py <worktree> <base> <file.py>... -- <test id>...
"""
import ast
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from common import git
from testrun import run

COPY_SKIP = (".git", "var", "__pycache__", ".venv", "venv", "node_modules", ".tox", ".mypy_cache", ".pytest_cache")


def mutants(source):
    """(line, replacement text, description) for every check in the file."""
    found = []
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.If) and node.body and isinstance(node.body[0], (ast.Raise, ast.Return))):
            continue
        text = ast.unparse(node.test)
        if text in ("__name__ == '__main__'", "'__main__' == __name__"):
            continue
        test = node.test
        start = offsets[test.lineno - 1] + len(lines[test.lineno - 1].encode()[:test.col_offset].decode())
        end = offsets[test.end_lineno - 1] + len(lines[test.end_lineno - 1].encode()[:test.end_col_offset].decode())
        variants = [("False", f"`{text}` replaced with False")]
        if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
            for i, part in enumerate(test.values):
                rest = [v for j, v in enumerate(test.values) if j != i]
                kept = rest[0] if len(rest) == 1 else ast.BoolOp(op=ast.Or(), values=rest)
                variants.append((ast.unparse(kept), f"`{ast.unparse(part)}` removed"))
        for replacement, description in variants:
            found.append((node.lineno, source[:start] + f"({replacement})" + source[end:], description))
    return found


def added_lines(worktree, base, name):
    """Line numbers the unit added to a file, or None when the whole file is new."""
    if git(worktree, "cat-file", "-e", f"{base}:{name}", check=False).returncode != 0:
        return None
    diff = git(worktree, "diff", "-U0", base, "--", name).stdout
    lines = set()
    for start, count in re.findall(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", diff, re.MULTILINE):
        lines.update(range(int(start), int(start) + int(count or 1)))
    return lines


def survivors(worktree, base, files, tests, timeout=300):
    worktree = Path(worktree)
    report = {"checks": 0, "survivors": [], "covered": []}
    for name in files:
        source = (worktree / name).read_text()
        added = added_lines(worktree, base, name)
        source_lines = source.splitlines()
        for line, mutated, description in mutants(source):
            if added is not None and line not in added:
                continue
            if "# covered:" in source_lines[line - 1]:
                report["covered"].append(f"{name}:{line} {source_lines[line - 1].split('# covered:', 1)[1].strip()}")
                continue
            report["checks"] += 1
            with tempfile.TemporaryDirectory(prefix="factory-mutant-") as scratch:
                copy = Path(scratch) / "tree"
                shutil.copytree(worktree, copy, ignore=shutil.ignore_patterns(*COPY_SKIP))
                (copy / name).write_text(mutated)
                try:
                    code = run(copy, tests, timeout=timeout)[0]
                except subprocess.TimeoutExpired:
                    code = "timeout"  # counted as caught
            if code in (0, 5):
                report["survivors"].append(f"{name}:{line} ({description})")
    return report


if __name__ == "__main__":
    split = sys.argv.index("--")
    result = survivors(sys.argv[1], sys.argv[2], sys.argv[3:split], sys.argv[split + 1:])
    print(json.dumps(result, indent=1))
    sys.exit(1 if result["survivors"] else 0)
