"""1.2.3, second review: model-written code is fenced (files, environment, secrets, time), the guard copies once,
commits carry the person's identity with hooks on, and a refused push says why."""
import json
import os
import subprocess
from pathlib import Path

import pytest
from conftest import GREEN, git, roles_project, unit_files, unit_worktree

import common
import guard
import land
import modelrun
import runners
import testrun

fenced = pytest.mark.skipif(testrun.FILESYSTEM_ISOLATION != "bwrap", reason="bubblewrap cannot start on this host")


@fenced
def test_a_test_run_cannot_write_outside_its_folder_or_see_the_home_folder(tmp_path, monkeypatch):
    work, outside, allowed = tmp_path / "work", tmp_path / "outside", tmp_path / "allowed"
    for folder in (work, outside, allowed):
        folder.mkdir()
    monkeypatch.setenv("FACTORY_ALLOW_PATHS", str(allowed))
    home = Path.home().resolve()
    # only the folders bound back in on purpose (Python's own folders, the factory) are visible in the home folder
    bound = {p.relative_to(home).parts[0] for p in [*testrun.readable_paths(), work, allowed] if home in p.parents}
    (work / "test_escape.py").write_text(
        "import os, pathlib, pytest\n"
        f"def test_cannot_write_outside():\n    with pytest.raises(OSError):\n        pathlib.Path({str(outside / 'x')!r}).write_text('x')\n"
        f"def test_home_is_hidden():\n    assert set(os.listdir({str(home)!r})) <= {bound!r}\n"
        f"    assert not pathlib.Path({str(home / '.ssh')!r}).exists()\n"
        f"    assert not pathlib.Path({str(home / '.config/gh')!r}).exists()\n"
        f"def test_allowed_path_is_writable():\n    pathlib.Path({str(allowed / 'ok')!r}).write_text('ok')\n"
        "def test_own_folder_is_writable():\n    pathlib.Path('here.txt').write_text('ok')\n")
    code, records, _, output = testrun.run(work)
    assert code == 0, output
    assert not (outside / "x").exists() and (allowed / "ok").exists() and (work / "here.txt").exists()


def test_a_hanging_test_is_stopped_and_counted_as_a_refusal(tmp_path):
    (tmp_path / "test_hang.py").write_text("import time\ndef test_hang():\n    time.sleep(60)\n")
    with pytest.raises(testrun.TestTimeout, match="limit of 2 seconds"):
        testrun.run(tmp_path, timeout=2)


def test_roles_get_an_allow_listed_environment_and_never_read_secret_files(monkeypatch, tmp_path):
    for name, value in (("AWS_SECRET_ACCESS_KEY", "aws"), ("GITHUB_TOKEN", "gh"), ("NPM_TOKEN", "npm"), ("LANG", "C.UTF-8")):
        monkeypatch.setenv(name, value)
    env = modelrun.claude_env("builder")
    assert "AWS_SECRET_ACCESS_KEY" not in env and "GITHUB_TOKEN" not in env and "NPM_TOKEN" not in env
    assert env["LANG"] == "C.UTF-8" and env["FACTORY_ROLE"] == "builder" and "PATH" in env
    command = modelrun.with_read_denies(["claude", "-p", "--allowedTools", "Read", "--disallowedTools", "WebFetch"])
    assert command.index("Read(~/.config/gh/**)") > command.index("--disallowedTools")
    for secret in ("Read(~/.ssh/**)", "Read(~/.netrc)", "Read(~/.config/factory/**)", "Read(~/.aws/**)", "Read(**/.env)"):
        assert secret in command


def test_the_builder_runs_tests_only_through_the_fenced_wrapper(make_repo, tmp_path):
    root = make_repo({"tests/test_ok.py": GREEN, **unit_files()})
    roles_project(root)
    folder = unit_worktree(root)
    seen = {}
    fake = tmp_path / "claude"
    fake.write_text("#!/bin/sh\ncat > /dev/null\necho '{\"type\":\"result\",\"subtype\":\"success\",\"is_error\":false,\"result\":\"x\"}'\n")
    fake.chmod(0o755)
    real_run = modelrun.run_tracked

    def spy(command, *args, **kwargs):
        seen["command"] = command
        return real_run([str(fake), *command[1:]], *args, **kwargs)
    runners.run_tracked = spy
    try:
        runners.make_runners(root)["build"]({"unit": ".ai/units/R1/1.json", "worktree": str(folder), "attempts": 0})
    finally:
        runners.run_tracked = real_run
    allowed = seen["command"][seen["command"].index("--allowedTools") + 1:seen["command"].index("--disallowedTools")]
    assert f"Bash(python3 {modelrun.RUN_TESTS} *)" in allowed
    assert not any("pytest" in rule for rule in allowed)
    assert "Read(~/.config/gh/**)" in seen["command"]


def test_the_guard_copies_the_work_folder_once_for_all_its_mutants(make_repo, monkeypatch):
    root = make_repo({"src/__init__.py": "", "tests/test_unit.py": "import pytest\nfrom src.newmod import go\n"
                      "def test_a():\n    with pytest.raises(ValueError):\n        go(None)\n"
                      "def test_b():\n    with pytest.raises(ValueError):\n        go(-1)\n"})
    base = git(root, "rev-parse", "HEAD")
    (root / "src/newmod.py").write_text("def go(x):\n    if x is None or x < 0:\n        raise ValueError('bad')\n    return 1\n")
    copies = []
    real = guard.shutil.copytree
    monkeypatch.setattr(guard.shutil, "copytree",  # copytree calls itself per subfolder: count whole-folder copies
                        lambda src, dst, *a, **k: (copies.append(1) if Path(src) == root else None) or real(src, dst, *a, **k))
    report = guard.survivors(root, base, ["src/newmod.py"], ["tests/test_unit.py::test_a", "tests/test_unit.py::test_b"])
    assert report["checks"] == 3 and report["survivors"] == [] and len(copies) == 1


def test_factory_commits_carry_the_persons_identity_and_a_refusing_hook_is_a_refusal(make_repo):
    root = make_repo({"x.txt": "x"})
    (root / "y.txt").write_text("y")
    git(root, "add", "y.txt")
    common.commit(root, "unit work")
    assert git(root, "log", "-1", "--format=%an <%ae>") == "Test Person <person@example.invalid>"
    hook = root / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\necho 'secret scanner: token found' >&2\nexit 1\n")
    hook.chmod(0o755)
    (root / "z.txt").write_text("z")
    git(root, "add", "z.txt")
    with pytest.raises(common.CommitRefused, match="secret scanner: token found"):
        common.commit(root, "more work")


def test_a_refused_push_says_why_and_only_a_moved_base_waits(make_repo, tmp_path):
    root = make_repo({"tests/test_ok.py": GREEN})
    bare = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(bare))
    git(root, "remote", "add", "origin", str(bare))
    git(root, "push", "-q", "origin", "main")
    git(root, "fetch", "-q", "origin")
    fetched = git(root, "rev-parse", "origin/main")
    (root / "f.py").write_text("X = 1\n")
    git(root, "add", "f.py")
    tested = common.commit(root, "unit")
    hook = bare / "hooks/pre-receive"
    hook.write_text("#!/bin/sh\necho 'GH006: Protected branch update failed' >&2\nexit 1\n")
    hook.chmod(0o755)
    with pytest.raises(land.PushRefused, match="GH006: Protected branch update failed"):
        land.push_direct(root, tested, "main", fetched)
    hook.unlink()
    with pytest.raises(land.MainMoved):
        land.push_direct(root, tested, "main", "0" * 40)  # the lease names a value main no longer has


def test_a_lock_owner_never_removes_a_lock_someone_else_took_over(tmp_path):
    path = tmp_path / "x.lock"
    with common.Lock(path, wait=1):
        path.write_text("1 someone-else")  # a takeover happened while this owner was away
    assert path.read_text() == "1 someone-else"
    with common.Lock(tmp_path / "y.lock", wait=1):
        pass
    assert not (tmp_path / "y.lock").exists()


@pytest.mark.parametrize("words", ["the quota check failed: QuotaExceeded", "server overloaded test fails",
                                   "rate limit reached for the widget"])
def test_a_failed_run_about_quotas_is_not_a_usage_limit(words):
    text = json.dumps({"type": "result", "subtype": "success", "is_error": True, "result": words})
    with pytest.raises(modelrun.RetryOnce):
        modelrun.classify(1, text, "")
