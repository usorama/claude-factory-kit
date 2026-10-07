"""Single-unit stop by code (hold and release), enqueue only from the live checkout, stale locks, and the
Chief of Staff role, its jobs and its launcher."""
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from conftest import CORE, GREEN, git, roles_project, unit_files

import common
import modelrun
import tick
from common import Lock, read_queue, write_queue

RED = "def test_{n}():\n    from src.newmod import go\n    assert go() == 1\n"


def unit_repo(make_repo):
    tests = "".join(RED.format(n=n) for n in "abc")
    root = make_repo({"tests/test_unit.py": tests, "tests/test_other.py": GREEN, "src/__init__.py": "",
                      "plan/backlog.md": "| ID | Status |\n|---|---|\n| R1 | building |\n", **unit_files()})
    roles_project(root)
    (root / "var/factory").mkdir(parents=True, exist_ok=True)
    write_queue(root, {"units": [{"unit": ".ai/units/R1/1.json", "worktree": str(root), "state": "red",
                                  "attempts": 0, "log": [], "estimate_minutes": 10}]})
    return root


def test_hold_ends_the_running_step_and_survives_its_save_then_release_needs_a_valid_recut(make_repo):
    root = unit_repo(make_repo)
    started = threading.Event()

    def slow_build(entry):
        started.set()
        result = modelrun.run_tracked(["sleep", "30"], root, "", dict(os.environ), 60,
                                      common.var(root) / "pids" / "R1-U1.pid")
        return False, f"builder exited {result.returncode}", {}

    runners = {step: slow_build for step in ("red", "build", "check", "review", "land", "watch")}
    clock = threading.Thread(target=lambda: tick.drive.tick(root, runners))
    begin = time.monotonic()
    with Lock(common.var(root) / "tick.lock", wait=5):  # stands in for the running tick's lock
        clock.start()
        assert started.wait(10)
        time.sleep(0.3)
        waiter = threading.Thread(target=lambda: results.append(tick.hold(root, ".ai/units/R1/1.json", "wrong brief")))
        results = []
        waiter.start()
        clock.join(20)
    waiter.join(20)
    assert time.monotonic() - begin < 15, "the runner was not ended"
    entry = read_queue(root)["units"][0]
    assert entry["hold"]["reason"] == "wrong brief" and entry["state"] == "red" and entry["attempts"] == 0
    assert results and results[0]["runner_ended"]
    assert tick.drive.tick(root, runners)["steps"] == 0  # a held unit is never run
    (root / "tests/test_unit.py").write_text(GREEN)  # a re-cut whose tests are not red
    with pytest.raises(tick.Refused, match="stays held"):
        tick.release(root, ".ai/units/R1/1.json", "re-cut")
    assert read_queue(root)["units"][0].get("hold")
    (root / "tests/test_unit.py").write_text("".join(RED.format(n=n) for n in "abc"))
    assert tick.release(root, ".ai/units/R1/1.json", "brief fixed")["released"]
    entry = read_queue(root)["units"][0]
    assert entry["state"] == "cut" and "hold" not in entry


def test_a_hold_set_after_the_tick_read_the_queue_survives_and_the_step_never_starts(make_repo):
    root = unit_repo(make_repo)
    stale = read_queue(root)["units"][0]  # what a tick read before the hold
    queue = read_queue(root)
    queue["units"][0]["hold"] = {"reason": "stop", "at": "now"}
    write_queue(root, queue)
    ran = []
    tick.drive.run_step(root, stale, {"build": lambda e: ran.append(1) or (True, "built", {})}, common.config(root))
    entry = read_queue(root)["units"][0]
    assert ran == [] and entry["hold"]["reason"] == "stop" and entry["state"] == "red"


def test_enqueue_hold_and_release_refuse_to_run_inside_a_unit_work_folder(make_repo, tmp_path):
    root = unit_repo(make_repo)
    git(root, "add", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@localhost", "commit", "-q", "-m", "x")
    folder = tmp_path / "unit-folder"
    git(root, "worktree", "add", "-q", "--detach", str(folder))
    with pytest.raises(tick.Refused, match="live checkout"):
        tick.enqueue(folder, ".ai/units/R1/1.json", folder)
    with pytest.raises(tick.Refused, match="live checkout"):
        tick.hold(folder, ".ai/units/R1/1.json", "x")


def test_a_lock_left_by_a_short_lived_or_reused_process_is_stale(tmp_path):
    finished = subprocess.Popen(["true"])
    finished.wait()
    (tmp_path / "x.lock").write_text(f"{finished.pid} 12345")
    with Lock(tmp_path / "x.lock", wait=1):
        pass
    (tmp_path / "x.lock").write_text(f"{os.getpid()} not-my-start-time")  # a reused pid
    with Lock(tmp_path / "x.lock", wait=1):
        pass
    (tmp_path / "x.lock").write_text(common.stamp(os.getpid()))  # a live owner holds it
    with pytest.raises(TimeoutError):
        with Lock(tmp_path / "x.lock", wait=0.3):
            pass


ROLE = CORE / "templates/prompts/chief-of-staff.v1.md"
JOBS = CORE / "templates/prompts/chief-of-staff-jobs.v1.md"


def test_the_chief_of_staff_names_its_duties_and_every_job_is_defined():
    role, jobs = ROLE.read_text(), JOBS.read_text()
    for heading in ("## What you own", "## How you decide", "## How you change state", "## What you report", "## Keeping going"):
        assert heading in role, heading
    for duty in ("Cut.", "Check every claim.", "Handle stops.", "Close rows.", "Retro.", "Front desk."):
        assert duty in role, duty
    for job in ("## tick", "## cut", "## verify", "## stop", "## review", "## close", "## retro", "## report"):
        assert job in jobs, job
    assert "Go back to the live checkout" in jobs and "never in the live one" in role
    assert "tick.py hold" in jobs and "tick.py release" in jobs


def test_the_generated_chief_agent_pins_an_exact_model_and_the_launcher_starts_role_and_loop(tmp_path):
    import agents_gen
    roles_project(tmp_path)
    roles = __import__("tomllib").loads((tmp_path / "factory.toml").read_text())["roles"]
    agents_gen.generate(roles, tmp_path, tmp_path)
    front = (tmp_path / ".claude/agents/chief-of-staff.md").read_text().split("---")[1]
    assert re.search(r"^model: claude-[a-z]+-\d+(-\d+)*$", front, re.M)
    (tmp_path / "factory").mkdir()
    for name in ("chief.sh", "common.py", "tomlw.py"):
        (tmp_path / "factory" / name).write_text((CORE / "factory" / name).read_text())
    (tmp_path / "factory/presets").mkdir()
    (tmp_path / "factory/presets/claude-only.toml").write_text((CORE / "factory/presets/claude-only.toml").read_text())
    printed = subprocess.run(["bash", "factory/chief.sh", "--print"], cwd=tmp_path, capture_output=True, text=True)
    assert printed.returncode == 0, printed.stderr
    assert "--agent chief-of-staff --model claude-sonnet-5-5" in printed.stdout and "/loop" in printed.stdout
    (tmp_path / "factory.toml").write_text((tmp_path / "factory.toml").read_text().replace('"claude-sonnet-5"', '"sonnet"'))
    refused = subprocess.run(["bash", "factory/chief.sh", "--print"], cwd=tmp_path, capture_output=True, text=True)
    assert refused.returncode != 0 and "refusing to start" in refused.stderr


def test_prune_keeps_a_folder_with_uncommitted_work_and_a_parked_units_branch(make_repo):
    from conftest import unit_worktree
    root = make_repo({"tests/test_ok.py": GREEN})
    landed, parked, dirty = unit_worktree(root, "R1", 1), unit_worktree(root, "R2", 1), unit_worktree(root, "R3", 1)
    (dirty / "notes.txt").write_text("a person's work in progress")
    (root / "var/factory").mkdir(parents=True, exist_ok=True)
    write_queue(root, {"units": [{"unit": f".ai/units/{r}/1.json", "worktree": str(w), "state": s, "attempts": 0, "log": []}
                                 for r, w, s in (("R1", landed, "landed"), ("R2", parked, "parked"), ("R3", dirty, "landed"))]})
    result = tick.prune(root)
    assert not landed.exists() and not parked.exists() and dirty.exists()
    assert (dirty / "notes.txt").read_text() == "a person's work in progress" and "uncommitted work" in result["kept"][0]
    branches = git(root, "branch", "--list", "unit/*")
    assert "unit/R2/1" in branches and "unit/R1/1" not in branches  # parked branch kept, merged landed branch deleted


def test_a_sabotage_copy_is_made_only_under_the_scratch_folder(make_repo, tmp_path):
    root = make_repo({"x.txt": "x"})
    with pytest.raises(tick.Refused, match="must be under"):
        tick.verify_checkout(root, ".ai/units/R1/1.json", tmp_path / "sabotage-R1")
    with pytest.raises(tick.Refused, match="has not landed"):  # the default folder passes the place check
        tick.verify_checkout(root, ".ai/units/R1/1.json")
