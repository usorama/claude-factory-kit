"""The restart switch: refuses without a fresh handoff note or with unsaved work, runs its steps in order,
never touches the clock, and starts itself detached from inside the session it restarts."""
import os
import subprocess
import time
from pathlib import Path

import pytest
from conftest import GREEN, git, roles_project

import common
import restart

FAKE_TMUX = """#!/bin/sh
echo "tmux $*" >> "$FAKE_STEPS"
case "$1" in
  display-message) echo "$FAKE_TMUX_SESSION" ;;
  new-session) touch "$FAKE_ALIVE" ;;
  kill-session) rm -f "$FAKE_ALIVE" ;;
  has-session) [ -f "$FAKE_ALIVE" ] ;;
esac
"""
FAKE_CLAUDE = """#!/bin/sh
echo "claude $*" >> "$FAKE_STEPS"
if [ "$1" = "update" ]; then echo 2.2.0 > "$FAKE_VERSION"; fi
if [ "$1" = "--version" ]; then cat "$FAKE_VERSION" 2>/dev/null || echo 2.1.290; fi
"""
FAKE_CRONTAB = "#!/bin/sh\necho \"crontab $*\" >> \"$FAKE_STEPS\"\n"


@pytest.fixture
def chief_repo(make_repo, tmp_path, monkeypatch):
    root = make_repo({"tests/test_ok.py": GREEN})
    roles_project(root)
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "factory files")
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(tmp_path / "origin.git"))
    git(root, "remote", "add", "origin", str(tmp_path / "origin.git"))
    git(root, "push", "-q", "-u", "origin", "main")
    fakes = tmp_path / "fakes"
    fakes.mkdir()
    for name, body in (("tmux", FAKE_TMUX), ("claude", FAKE_CLAUDE), ("crontab", FAKE_CRONTAB)):
        (fakes / name).write_text(body)
        (fakes / name).chmod(0o755)
    monkeypatch.setenv("PATH", f"{fakes}{os.pathsep}{os.environ['PATH']}")
    for name, value in (("FAKE_STEPS", tmp_path / "steps.log"), ("FAKE_ALIVE", tmp_path / "alive"),
                        ("FAKE_VERSION", tmp_path / "version"), ("FAKE_TMUX_SESSION", "something-else")):
        monkeypatch.setenv(name, str(value))
    monkeypatch.setenv("FACTORY_RESTART_WAIT", "0")
    monkeypatch.delenv("TMUX", raising=False)
    return root


def handoff(root, minutes_old=1):
    folder = common.var(root) / "handoff"
    folder.mkdir(parents=True, exist_ok=True)
    note = folder / "2026-10-07T10-00.md"
    note.write_text("# Handoff\nRestart: none running.\n")
    then = time.time() - minutes_old * 60
    os.utime(note, (then, then))
    return note


def steps():
    path = Path(os.environ["FAKE_STEPS"])
    return path.read_text().splitlines() if path.exists() else []


@pytest.mark.parametrize("spoil, reason", [
    (lambda root: None, "no chief handoff note"),
    (lambda root: handoff(root, minutes_old=31), "minutes old"),
    (lambda root: (handoff(root), (root / "tests/test_ok.py").write_text("changed\n")), "uncommitted changes"),
    (lambda root: (handoff(root), (root / "x.txt").write_text("x"), git(root, "add", "x.txt"),
                   git(root, "commit", "-q", "-m", "local")), "not pushed"),
])
def test_a_restart_is_refused_without_a_fresh_handoff_or_with_unsaved_work(chief_repo, spoil, reason, capsys):
    spoil(chief_repo)
    assert restart.main([], root=chief_repo) == 1
    assert reason in capsys.readouterr().err
    assert not any(s.startswith(("tmux new", "tmux kill", "claude update")) for s in steps())  # nothing changed
    assert f"STOP: " in (common.var(chief_repo) / "restart.log").read_text()


def test_a_restart_runs_its_steps_in_order_and_never_touches_the_clock(chief_repo, capsys):
    handoff(chief_repo)
    assert restart.main([], root=chief_repo) == 0
    shown = capsys.readouterr().out
    assert shown.index("factory restart will:") < shown.index("1. check passed")
    order = [s.split()[0] + " " + s.split()[1] for s in steps()]
    assert order == ["claude --version", "claude update", "claude --version", "tmux kill-session", "tmux new-session",
                     "tmux has-session"]
    assert "factory/chief.sh" in next(s for s in steps() if s.startswith("tmux new-session"))
    assert not any(s.startswith("crontab") for s in steps())
    record = (common.var(chief_repo) / "restart.log").read_text()
    assert "before '2.1.290', after '2.2.0'" in record and "4. OK" in record
    assert restart.main(["--no-update"], root=chief_repo) == 0
    assert sum(s.startswith("claude update") for s in steps()) == 1


def test_check_only_reports_and_inside_the_session_it_starts_itself_detached(chief_repo, monkeypatch, capsys):
    handoff(chief_repo)
    assert restart.main(["--check"], root=chief_repo) == 0 and "safe to restart" in capsys.readouterr().out
    assert steps() == []
    started = []
    monkeypatch.setenv("TMUX", "/tmp/tmux-1/default,1,0")
    monkeypatch.setenv("FAKE_TMUX_SESSION", "factory-chief")
    monkeypatch.setattr(restart, "detach", lambda command, root: started.append(command))
    assert restart.main([], root=chief_repo) == 0
    assert started and started[0][-1] == "--detached" and "Started in the background" in capsys.readouterr().out
    assert not any(s.startswith(("tmux new", "tmux kill")) for s in steps())
