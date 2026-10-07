#!/usr/bin/env python3
"""The restart switch: update the agent harness and restart the chief of staff session, the same way every time.

Only a person runs it (no model is allowed to: the settings deny it, and no command pre-approves it).
  factory restart              show the steps, then run them
  factory restart --check      run only the safety check and print the result; change nothing
  factory restart --force      skip the safety check (the person accepts losing unsaved chief work)
  factory restart --no-update  restart without updating the harness
Steps, each written to var/factory/restart.log:
  1. safety check: a chief handoff note under var/factory/handoff/ less than handoff_max_minutes old (default 30),
     no uncommitted change to a tracked file, no local commit that is not pushed;
  2. update the harness: harness_update_command in factory.toml (default "claude update" for a claude chief,
     "none" to skip), with the version before and after;
  3. restart the chief: close the tmux session chief_session (default "factory-chief") and start it again with
     factory/chief.sh, the launcher that starts the role AND its loop;
  4. check the session is alive after restart_wait_seconds (default 60).
It never touches the clock (cron, launchd or Task Scheduler): units keep moving while the chief restarts.
Started from inside the session it restarts, it first starts itself again detached, because closing that session
would end it halfway.
The chief's first tick after a restart reads the newest handoff note and this log (job tick, step 0).
"""
import argparse
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from common import config, git, log, now, var  # noqa: E402


class RestartRefused(RuntimeError):
    """The safety check failed; nothing was changed."""


def settings(root):
    cfg = config(root)
    tool = cfg["roles"]["chief-of-staff"]["tool"]
    update = cfg["harness_update_command"] or ("claude update" if tool == "claude" else "none")
    return {"tool": tool, "session": cfg["chief_session"], "update": update,
            "max_minutes": float(cfg["handoff_max_minutes"]), "base": cfg["base"],
            "wait": float(os.environ.get("FACTORY_RESTART_WAIT", cfg["restart_wait_seconds"]))}


def write(root, text):
    line = f"{now()} {text}"
    with (var(root) / "restart.log").open("a") as stream:
        stream.write(line + "\n")
    print(line)


def newest_handoff(root):
    notes = sorted((var(root) / "handoff").glob("*.md"), key=lambda p: p.stat().st_mtime)
    return notes[-1] if notes else None


def safety(root, s):
    """The reasons not to restart now: [] when it is safe."""
    reasons = []
    note = newest_handoff(root)
    age = (time.time() - note.stat().st_mtime) / 60 if note else None
    if note is None:
        reasons.append("no chief handoff note in var/factory/handoff/: ask the chief to run job handoff first")
    elif age > s["max_minutes"]:
        reasons.append(f"the newest handoff note ({note.name}) is {age:.0f} minutes old (limit {s['max_minutes']:.0f}): "
                       "ask the chief to run job handoff again")
    dirty = [line for line in git(root, "status", "--porcelain", "--untracked-files=no").stdout.splitlines() if line]
    if dirty:
        reasons.append(f"uncommitted changes to tracked files ({dirty[0].strip()}, {len(dirty)} in all)")
    git(root, "fetch", "-q", "origin", check=False)
    upstream = git(root, "rev-parse", "--abbrev-ref", "@{u}", check=False).stdout.strip() or f"origin/{s['base']}"
    ahead = git(root, "rev-list", "--count", f"{upstream}..HEAD", check=False)
    if ahead.returncode:
        reasons.append(f"cannot compare with {upstream}: is the branch pushed?")
    elif int(ahead.stdout.strip() or 0):
        reasons.append(f"{ahead.stdout.strip()} local commit(s) not pushed to {upstream}")
    return reasons, note


def plan_lines(s, update):
    return [f"1. safety check: a handoff note under {s['max_minutes']:.0f} minutes old, a clean and pushed checkout",
            f"2. update the harness: {s['update'] if update and s['update'] != 'none' else 'skipped'}",
            f"3. restart tmux session {s['session']} with factory/chief.sh (the chief role and its loop)",
            f"4. check the session is alive after {s['wait']:.0f} seconds",
            "The clock is not touched."]


def version(tool):
    out = subprocess.run([tool, "--version"], capture_output=True, text=True)
    return out.stdout.strip() or out.stderr.strip() or f"exit {out.returncode}"


def inside_the_session(session):
    if not os.environ.get("TMUX"):
        return False
    out = subprocess.run(["tmux", "display-message", "-p", "#S"], capture_output=True, text=True)
    return out.stdout.strip() == session


def detach(command, root):
    """Start command in its own session, so closing the chief's tmux session does not end it."""
    with (var(root) / "restart.log").open("a") as stream:
        subprocess.Popen(command, cwd=root, stdout=stream, stderr=stream, stdin=subprocess.DEVNULL, start_new_session=True)


def restart(root, check=False, force=False, update=True):
    root = Path(root).resolve()
    s = settings(root)
    reasons, note = safety(root, s)
    if check:
        for line in reasons or [f"safe to restart: handoff {note.name}, checkout clean and pushed"]:
            print(line)
        return 1 if reasons else 0
    write(root, f"restart requested (force={force}, update={update})")
    if reasons and not force:
        for reason in reasons:
            write(root, f"STOP: {reason}")
        raise RestartRefused("; ".join(reasons))
    write(root, f"1. check {'skipped with --force: ' + '; '.join(reasons) if reasons else 'passed: ' + note.name}")
    before = version(s["tool"])
    if update and s["update"] != "none":
        done = subprocess.run(shlex.split(s["update"]), capture_output=True, text=True)
        write(root, f"2. {s['update']}: exit {done.returncode} {(done.stdout + done.stderr).strip()[-300:]}")
    else:
        write(root, "2. harness update skipped")
    after = version(s["tool"])
    write(root, f"   harness version before '{before}', after '{after}'")
    subprocess.run(["tmux", "kill-session", "-t", s["session"]], capture_output=True)
    started = subprocess.run(["tmux", "new-session", "-d", "-s", s["session"], "-c", str(root),
                              "bash", str(root / "factory/chief.sh")], capture_output=True, text=True)
    write(root, f"3. session {s['session']} restarted with factory/chief.sh: exit {started.returncode} {started.stderr.strip()}")
    time.sleep(s["wait"])
    alive = subprocess.run(["tmux", "has-session", "-t", s["session"]], capture_output=True).returncode == 0
    log(root, event="restart", ok=alive, harness=after, note=note.name if note else "")
    if not alive:
        write(root, f"4. FAILED: session {s['session']} is not running. Start it by hand: "
                    f"tmux new-session -d -s {s['session']} -c {shlex.quote(str(root))} bash factory/chief.sh")
        return 1
    write(root, f"4. OK: session {s['session']} is running on '{after}'. The clock was not touched.")
    return 0


def main(argv=None, root=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-update", action="store_true")
    parser.add_argument("--detached", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = Path(root or HERE.parent)
    var(root).mkdir(parents=True, exist_ok=True)
    s = settings(root)
    if not args.check and not args.detached:
        print("factory restart will:\n  " + "\n  ".join(plan_lines(s, not args.no_update)))
        if inside_the_session(s["session"]):
            rest = list(argv if argv is not None else sys.argv[1:])
            detach([sys.executable, str(Path(__file__).resolve()), *rest, "--detached"], root)
            print(f"Started in the background, because this session is the one it restarts. "
                  f"Follow it with: tail -f {var(root) / 'restart.log'}")
            return 0
    try:
        return restart(root, args.check, args.force, not args.no_update)
    except RestartRefused as error:
        print(f"restart refused, nothing changed: {error}. Use --force to restart anyway.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
