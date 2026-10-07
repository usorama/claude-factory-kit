import json
import subprocess
import sys
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[1]
FACTORY = CORE / "factory"
sys.path.insert(0, str(FACTORY))
sys.path.insert(1, str(CORE))

GREEN = "def test_ok():\n    assert True\n"


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def make_repo(tmp_path):
    """make_repo(files) -> a committed git repo holding the files, with a unit and brief helper."""
    def make(files, name="repo"):
        root = tmp_path / name
        for path, text in files.items():
            (root / path).parent.mkdir(parents=True, exist_ok=True)
            (root / path).write_text(text)
        git(root, "init", "-q", "-b", "main")
        git(root, "config", "user.name", "Test Person")  # the factory commits as the person: give them an identity
        git(root, "config", "user.email", "person@example.invalid")
        git(root, "add", "-A")
        git(root, "-c", "user.name=t", "-c", "user.email=t@localhost", "commit", "-q", "-m", "seed")
        return root
    return make


def unit_files(row="R1", n=1, tests=("a", "b", "c"), files=("src/newmod.py",), test_file="tests/test_unit.py",
               brief_extra=""):
    unit = {"row": row, "n": n, "title": "t", "paragraph": "Does one thing. Sabotage: remove it.", "seam": "go()",
            "files": list(files), "out_of_scope": "nothing else", "estimate_minutes": 10,
            "tests": [f"{test_file}::test_{t}" for t in tests]}
    return {f".ai/units/{row}/{n}.json": json.dumps(unit),
            f".ai/specs/{row}-U{n}.md": brief(unit["tests"][0], brief_extra)}


def brief(named_test, extra="", drop=None):
    sections = {n: f"## {n}. Part {n}\n- text\n" for n in range(1, 9)}
    sections[2] = f"## 2. Where the truth lives\n- The unit file.\n{extra}\n"
    sections[5] = f"## 5. How to prove it\n- Named test: {named_test}\n- Named sabotage: remove the check; that test goes red.\n"
    return "# Brief\n\n" + "".join(text for n, text in sections.items() if n != drop)


WORK_PC = ["claude-sonnet-5-5", "claude-sonnet-5", "claude-sonnet-4-6", "claude-haiku-5"]


def roles_project(root, answered=WORK_PC, preset="claude-only", edit=None):
    """Write .ai/prompts and a factory.toml mapped from a probe report in which only `answered` replied."""
    import shutil
    import probe
    shutil.copytree(CORE / "templates/prompts", Path(root) / ".ai/prompts", dirs_exist_ok=True)
    report = {"at": "2026-10-07T00:00:00+00:00",
              "tools": {"claude": {"available": True, "answered": [m for m in answered if m.startswith("claude")]},
                        "codex": {"available": True, "answered": [m for m in answered if m.startswith("gpt")]}}}
    text, rows = probe.roles_file(probe.load_preset(preset), report)
    (Path(root) / "factory.toml").write_text(text if edit is None else edit(text))
    (Path(root) / ".factory-clone").write_text("")  # a test project stands in for the factory's own clone
    import protect
    protect.snapshot(root)  # as init does: the person approved this roles file
    return rows


@pytest.fixture
def clock_repo(make_repo, tmp_path):
    """A committed repo with a bare origin, so the tick's fetch works, and a valid roles file."""
    root = make_repo({"plan/backlog.md": "| ID | Status |\n|---|---|\n| R0 | building |\n"}, "clock")
    roles_project(root)
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(tmp_path / "origin.git"))
    git(root, "remote", "add", "origin", str(tmp_path / "origin.git"))
    git(root, "push", "-q", "origin", "main")
    return root


def plan_matrix(*rows):
    """A valid plan/slice-matrix.json whose slices are the given rows."""
    return json.dumps({
        "source": {"description": "Test plan.", "requirements": ["REQ1"],
                   "outcomes": [{"id": "O1", "text": "Users get the result.", "requirements": ["REQ1"], "first_proof": rows[0]}],
                   "features": ["The feature"]},
        "engines": [],
        "slices": [{"id": row, "title": f"Row {row}", "behavior": "A user sees the result.", "layers_touched": ["code", "tests"],
                    "acceptance": [{"check": "The tests pass.", "type": "yes_no", "command": "python3 -m pytest -q passes"}],
                    "blocked_by": [], "size": "S", "est_hours": 1, "covers": ["REQ1"], "engines": {}, "outcomes": ["O1"]}
                   for row in rows]})


def unit_worktree(root, row="R1", n=1):
    """Commit everything and make the unit's work folder the way the clock requires: <repo>-worktrees/<row>-U<n>."""
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@localhost", "commit", "-q", "--allow-empty", "-m", "cut")
    folder = Path(root).parent / f"{Path(root).name}-worktrees" / f"{row}-U{n}"
    git(root, "worktree", "add", "-q", "-b", f"unit/{row}/{n}", str(folder))
    return folder
