"""1.2.3, second review M12 and L4: the clock is installed through a wrapper with quoted paths, the person's
other cron jobs are never lost, and gh is required only when units land through pull requests."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1] / "factory"
FAKE_CRONTAB = """#!/bin/sh
store="$FAKE_CRON_STORE"
if [ "$1" = "-l" ]; then
  if [ -n "$FAKE_CRON_FAIL" ]; then echo "$FAKE_CRON_FAIL" >&2; exit 1; fi
  if [ -f "$store" ]; then cat "$store"; else echo "no crontab for person" >&2; exit 1; fi
elif [ "$1" = "-" ]; then cat > "$store"; fi
"""
FAKE_GH = "#!/bin/sh\necho \"$*\" >> \"$FAKE_GH_LOG\"\nexit 1\n"  # never signed in
STUB_TICK = '#!/usr/bin/env bash\nmkdir -p "$1/var/factory"\necho "tick for [$1]" >> "$1/var/factory/ticks.log"\n'


def clock_repo(tmp_path, landing='landing = "direct"\n', origin=None):
    repo = tmp_path / "my work repo"
    (repo / "factory").mkdir(parents=True)
    shutil.copy2(KIT / "install-clock.sh", repo / "factory/install-clock.sh")
    (repo / "factory/tick.sh").write_text(STUB_TICK)
    (repo / "factory/consistency.py").write_text("")
    (repo / "factory.toml").write_text(landing + '[roles.builder]\ntool = "claude"\n')
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    if origin:
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", origin], check=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (("crontab", FAKE_CRONTAB), ("gh", FAKE_GH), ("claude", "#!/bin/sh\nexit 0\n")):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    home = tmp_path / "home"
    home.mkdir()
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "HOME": str(home), "FAKE_CRON_STORE": str(tmp_path / "crontab.txt"),
           "FAKE_GH_LOG": str(tmp_path / "gh.log")}
    return repo, env


def install(repo, env):
    return subprocess.run(["bash", str(repo / "factory/install-clock.sh"), str(repo)], env=env,
                          capture_output=True, text=True)


@pytest.mark.skipif(os.uname().sysname != "Linux", reason="the cron path is the Linux path")
def test_a_repo_path_with_a_space_installs_a_quoted_clock_and_keeps_other_jobs(tmp_path):
    repo, env = clock_repo(tmp_path)
    store = Path(env["FAKE_CRON_STORE"])
    store.write_text("0 1 * * * /usr/bin/backup --nightly\n*/5 * * * * /bin/bash /old/factory/tick.sh /old\n")
    done = install(repo, env)
    assert done.returncode == 0, done.stderr + done.stdout
    lines = store.read_text().splitlines()
    assert "0 1 * * * /usr/bin/backup --nightly" in lines  # the person's own job survives
    clock = [line for line in lines if "clock-run.sh" in line]
    assert len(clock) == 1 and "'" in clock[0]
    # run the cron command exactly as cron would (through /bin/sh) and see the tick get the whole path
    (repo / "var/factory/ticks.log").unlink()
    subprocess.run(["/bin/sh", "-c", clock[0].split(" ", 5)[5]], env=env, check=True)
    assert (repo / "var/factory/ticks.log").read_text().strip() == f"tick for [{repo}]"
    assert not Path(env["FAKE_GH_LOG"]).exists()  # direct landing: gh is never asked


def test_a_failing_crontab_read_changes_nothing(tmp_path):
    repo, env = clock_repo(tmp_path)
    store = Path(env["FAKE_CRON_STORE"])
    store.write_text("0 1 * * * /usr/bin/backup --nightly\n")
    env["FAKE_CRON_FAIL"] = "crontab: cannot open /var/spool/cron: Permission denied"
    done = install(repo, env)
    assert done.returncode != 0 and "crontab was not changed" in done.stderr
    assert store.read_text() == "0 1 * * * /usr/bin/backup --nightly\n"


def test_gh_is_required_only_when_units_land_through_pull_requests(tmp_path):
    repo, env = clock_repo(tmp_path, landing="", origin="git@github.com:someone/thing.git")
    done = install(repo, env)
    assert done.returncode != 0 and "gh is not signed in" in done.stderr and "pr_merge" in done.stderr
